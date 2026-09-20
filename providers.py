# -*- coding: utf-8 -*-
"""行情数据源。

widget.py 只认三个入口：fetch_quotes / search_stocks / fetch_spark，
具体走腾讯还是新浪由这里决定：主源挂了自动切备源，下一次仍从上次成功的源开始。

加新源 = 写一个 Provider 子类 + 注册进 PROVIDERS，别处一行都不用改。
"""
import json
import math
import re
import urllib.parse
import urllib.request

import market_clock

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
# 新浪没 Referer 直接 403，这是它和腾讯最大的区别
SINA_HEADERS = {"Referer": "https://finance.sina.com.cn"}

# ETF / 场内基金报 3 位小数，其余 2 位
FUND_PREFIX = ("51", "52", "56", "58", "50", "15", "16", "159", "588", "518")

NORMAL = "normal"
HALT = "halt"               # 停牌：有昨收但一股没成交
LIMIT_UP = "limit_up"       # 涨停
LIMIT_DN = "limit_dn"       # 跌停

STATUS_TEXT = {HALT: "停牌", LIMIT_UP: "涨停", LIMIT_DN: "跌停"}


HTTP_TIMEOUT = 5      # 单个源的请求超时（秒）


def http_get(url, timeout=HTTP_TIMEOUT, headers=None):
    h = dict(UA)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------- 归一化的小工具 ----------------

def _num(v, default=0.0):
    """网络字段转 float。凡是来自网络的数字，一律 finite-aware。

    只挡 NaN 是不够的，两种东西会从缝里漏进来：
      - `1e999` 这种写法 float() 老实解析成 inf
      - 超大整数（JSON 里的 400 位数字）float() 直接抛 **OverflowError**

    它们一旦进了 price / prev / pct / 涨跌停比较，后面全是 inf 传播：
    涨跌额变 inf、盈亏算不出来、绘制时格式化出 "inf"。既然这一层就是
    "把不可信的东西变成可信的"的边界，就该在这里挡干净。

    default 传 None 时表示"这一项没有"，调用方用它过滤掉废点（分时线在用）。
    """
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        return default
    return f if math.isfinite(f) else default


def _opt_num(v):
    """字段转 float，但**"没给"**和**"给了 0"**必须分开。

        missing（字段不存在 / 空串）  -> None
        malformed（"abc" / "--"）     -> None
        NaN / ±inf                    -> None
        真实的 "0"                    -> 0.0

    成交量是唯一需要区分的字段：截断响应里根本没有成交量那一列，拿它当 0
    会让 quote_status 判成"今天一股没成交 → 停牌"，界面上价格直接变 `--`、
    涨跌额和盈亏一起被藏掉。

    同理，接口给了个畸形值（"--" 是真实见过的占位符）也不代表成交量真是 0
    —— 那只是"这一列读不出来"。没给就是没给，不能替它回答"是 0"。
    """
    if v is None:
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return f if math.isfinite(f) else None


def _field(f, i):
    """按位置取字段，越界返回空串。

    接口偶尔会返回被截断的行：字段数够 35 但不到 49，直接 f[47] 会抛
    IndexError，整轮取数就废了。宁可少拿两个涨跌停价（后面有 guess_limit 兜底）。
    """
    return f[i] if 0 <= i < len(f) else ""


def decimals_of(code):
    return 3 if (code or "").startswith(FUND_PREFIX) else 2


def guess_limit(code, name, prev):
    """按板块算涨跌停价，返回 (涨停价, 跌停价)。

    腾讯直接给，新浪不给，所以要有这个兜底。认不出板块就按主板 10%。
    创业板 / 科创板 20%，北交所 30%，主板 ST 5%（创业板科创板被 ST 仍是 20%）。
    """
    if prev <= 0:
        return 0.0, 0.0
    code = code or ""
    if code.startswith(("30", "688")):
        pct = 0.20
    elif code.startswith(("8", "43", "92", "920")):
        pct = 0.30
    elif "ST" in (name or "").upper():
        pct = 0.05
    else:
        pct = 0.10
    return round(prev * (1 + pct), 2), round(prev * (1 - pct), 2)


def quote_status(price, volume, limit_up, limit_dn, trust_limits=True):
    """停牌 / 涨停 / 跌停 / 正常，一次性判好，调用方不用再算。

    停牌的判据是「今天该有成交却一股没有」。盘前成交量必然是 0，
    那时不算停牌（见 market_clock.has_session_started）。

    volume 为 None 表示"这一列接口没给"（响应被截断或畸形），**不是**成交量为 0，
    这种情况不许判停牌 —— 那会把一只正常交易的股票显示成停牌。

    ★ trust_limits=False 表示涨跌停价**不是接口给的**，是我们按板块规则
    推算的（新浪不给这两个字段）。这时不产生 LIMIT_UP / LIMIT_DN ——
    只保留停牌判定，其余一律 NORMAL。

    理由：guess_limit() 是近似规则（主板 10% / ST 5% / 创业板科创板 20% /
    北交所 30%），覆盖不了上市初期无涨跌幅限制、特殊交易状态、临时规则、
    取整差异。它算出来的价被拿去当判据，等于把近似值包装成一个看起来
    确定的「涨停」徽标，用户还看不出那是估的。**不确定就少说。**
    """
    if price <= 0:
        return HALT
    if trust_limits:
        if limit_up > 0 and price >= limit_up - 1e-6:
            return LIMIT_UP
        if limit_dn > 0 and price <= limit_dn + 1e-6:
            return LIMIT_DN
    if volume is not None and volume <= 0 and market_clock.has_session_started():
        return HALT
    return NORMAL


def make_quote(full, code, name, price, prev, high=0.0, low=0.0, open_=0.0,
               volume=None, stamp="", limit_up=0.0, limit_dn=0.0, provider=""):
    """把各家字段整理成统一结构。昨收都没有说明这行是废数据，返回 None。

    full（sh600519 这种带市场的完整代码）是唯一身份：sh000001 和 sz000001
    的 6 位 code 都是 000001，只看 code 会撞车。

    provider 记这行**是谁给的**（"tencent" / "sina"）：一屏里可能混着两个源的
    数据（主源漏一只、备源补上），出了偏差要能问出"这行是哪个源来的"，
    不然只能靠猜。

    limit_estimated 记涨跌停价**是不是推算的**：腾讯直接给，新浪不给、由
    guess_limit 按板块算。算出来的可能和交易所实际（比如 ST 摘帽、临停后
    调整）不一致，标出来才不会被人当成权威值引用。
    """
    prev = _num(prev)
    if prev <= 0 or not code or not full:
        return None
    price = _num(price)
    # 全部先转成数字：接口给的是字符串，直接往下传会让
    # quote_status 里的 "volume <= 0" 拿字符串和 int 比，抛 TypeError
    high = _num(high)
    low = _num(low)
    open_ = _num(open_)
    volume = _opt_num(volume)      # None = 这一列没给，别当成 0
    limit_up = _num(limit_up)
    limit_dn = _num(limit_dn)
    limit_given = limit_up > 0 and limit_dn > 0
    if not limit_given:
        limit_up, limit_dn = guess_limit(code, name, prev)
    return {
        "full": full,
        "code": code,
        "name": name or code,
        "decimals": decimals_of(code),
        "price": price,
        "prev": prev,
        "change": price - prev,
        "pct": (price - prev) / prev * 100,
        "high": high,
        "low": low,
        "open": open_,
        "volume": volume,
        "time": stamp or "",
        "limit_up": limit_up,
        "limit_dn": limit_dn,
        "limit_estimated": not limit_given,
        "provider": provider or "",
        # 推算出来的涨跌停价只留作参考，不参与 authoritative 的涨跌停判定
        "status": quote_status(price, volume, limit_up, limit_dn,
                               trust_limits=limit_given),
    }


# ---------------- 数据源 ----------------

class Provider:
    """一个数据源。quotes() 必须实现；search / spark 有就实现，没有就用默认空实现。"""
    key = ""
    label = ""

    def quotes(self, codes):
        raise NotImplementedError

    def search(self, keyword, limit=8):
        return []

    def spark(self, code):
        return None


class TencentProvider(Provider):
    """腾讯财经。字段最全，涨跌停价直接给，所以当主源。"""
    key = "tencent"
    label = "腾讯"

    def quotes(self, codes):
        if not codes:
            return []
        url = "https://qt.gtimg.cn/q=" + ",".join(codes)
        raw = http_get(url).decode("gbk", errors="ignore")
        out = []
        for line in raw.split(";"):
            # 从响应变量名 v_sh600519 里取完整代码 —— 不能按请求顺序补，
            # 漏返回一只或顺序变了就会串股
            m = re.match(r'^v_([a-z]{2}\d{6})="(.*)"$', line.strip())
            if not m:
                continue
            full, body = m.group(1), m.group(2)
            f = body.split("~")
            if len(f) < 35:
                continue
            q = make_quote(full, f[2], f[1], f[3], f[4],
                           high=f[33], low=f[34], open_=f[5],
                           # f[36] 用 _field：接口偶尔给截断的响应，len(f) 正好
                           # 35 或 36 时直接取 f[36] 会 IndexError，把整只丢掉
                           volume=_field(f, 36), stamp=f[30],
                           limit_up=_num(_field(f, 47)),
                           limit_dn=_num(_field(f, 48)),
                           provider=self.key)
            if q:
                out.append(q)
        return out

    def search(self, keyword, limit=8):
        """支持拼音缩写(mt) / 代码(600519) / 全名(茅台)。
        返回 v_hint="市场~代码~名称~拼音~类型^..."，无结果为 N

        t=gp 而不是 t=all：all 会把港股(hk)、美股(us)一起返回，
        我们只做 A 股，没必要去拉那些数据再丢掉。实测 gp 已经覆盖
        A 股 / 指数 / ETF（515220、000001、399006 都能搜到），
        唯一搜不到的是北交所 —— 那是腾讯接口本身的限制，all 也一样。
        """
        kw = (keyword or "").strip()
        if not kw:
            return []
        url = "https://smartbox.gtimg.cn/s3/?q=" + urllib.parse.quote(kw) + "&t=gp"
        raw = http_get(url).decode("utf-8", errors="ignore")
        m = re.search(r'v_hint="(.*?)"', raw)
        if not m or m.group(1) == "N":
            return []
        body = m.group(1)
        if "\\u" in body:                       # 接口返回 \uXXXX 字面量，得解码
            try:
                body = json.loads('"' + body.replace('"', '\\"') + '"')
            except Exception:
                pass
        # 腾讯用 ~ 分字段、^ 分条
        return _clean_search([_row5(f.split("~")) for f in body.split("^")], limit)

    def spark(self, code):
        url = "https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=" + code
        data = json.loads(http_get(url).decode("utf-8", errors="ignore"))
        node = data["data"][code]["data"]
        arr = node["data"] if isinstance(node, dict) else node
        pts = []
        for item in arr:
            p = item.split()
            if len(p) >= 2:
                pts.append(_num(p[1], None))
        pts = [v for v in pts if v is not None]
        return pts if len(pts) >= 2 else None


class SinaProvider(Provider):
    """新浪财经。备源：字段比腾讯少（没有涨跌停价），但接口更稳。"""
    key = "sina"
    label = "新浪"

    def quotes(self, codes):
        if not codes:
            return []
        url = "https://hq.sinajs.cn/list=" + ",".join(codes)
        raw = http_get(url, headers=SINA_HEADERS).decode("gbk", errors="ignore")
        out = []
        for line in raw.split(";"):
            line = line.strip()
            mark = line.find("hq_str_")
            if mark < 0 or '="' not in line:
                continue
            full = line[mark + 7: line.find('="')]
            # 从变量名里抠出来的必须真是 sh600519 这种格式，否则就是脏行
            if not re.fullmatch(r"[a-z]{2}\d{6}", full):
                continue
            f = line[line.find('="') + 2: line.rfind('"')].split(",")
            if len(f) < 32 or not f[0]:
                continue
            # 新浪给股，腾讯给手，统一成手。成交量列是空串时保持 None（没给），
            # 不要除成 0.0 —— 那会被当成停牌
            vol = _opt_num(f[8])
            q = make_quote(full, full[2:] or full, f[0], f[3], f[2],
                           high=f[4], low=f[5], open_=f[1],
                           volume=(None if vol is None else vol / 100.0),
                           stamp=(f[30] + f[31]).replace("-", "").replace(":", ""),
                           provider=self.key)
            if q:
                out.append(q)
        return out

    def search(self, keyword, limit=8):
        kw = (keyword or "").strip()
        if not kw:
            return []
        # type=11 就是沪深京 A 股 / 指数。逐个实测过各取值的含义：
        #   12 = B 股（900950 新城B股）、21/22 = 场外基金（of 前缀，ETF 联接之类）
        #   15/16 = 现在返回空
        # 只做 A 股，所以只要 11。ETF 在两边都搜不到代码（新浪本来就不行，
        # 腾讯靠 t=gp 走），这是接口本身的限制，不是参数能救的。
        url = ("https://suggest3.sinajs.cn/suggest/type=11&key="
               + urllib.parse.quote(kw))
        raw = http_get(url).decode("gbk", errors="ignore")
        m = re.search(r'suggestvalue="(.*?)"', raw)
        if not m:
            return []
        # 新浪用 , 分字段、; 分条，每条是 名称,类型,代码,sh600519,名称,...
        recs = []
        for item in m.group(1).split(";"):
            f = item.split(",")
            if len(f) >= 4:
                # f[0] 在按代码搜时是 "sh600519"、按名称搜时才是名字，f[4] 才恒为名称
                recs.append((f[3][:2], f[3][2:], (f[4] if len(f) > 4 else "") or f[0], "", ""))
        return _clean_search(recs, limit)

    def spark(self, code):
        """新浪没有分时接口，用 5 分钟 K 线的收盘价凑一条走势。"""
        url = ("https://quotes.sina.cn/cn/api/json_v2.php/"
               "CN_MarketDataService.getKLineData?symbol=%s&scale=5&ma=no&datalen=48" % code)
        arr = json.loads(http_get(url, headers=SINA_HEADERS).decode("utf-8", errors="ignore"))
        pts = [_num(it.get("close"), None) for it in arr]
        pts = [v for v in pts if v is not None]
        return pts if len(pts) >= 2 else None


def _row5(f):
    """搜索结果取前 5 个字段（市场, 代码, 名称, 拼音, 类型），不够就补空串。"""
    f = list(f) + [""] * (5 - len(f))
    return f[0], f[1], f[2], f[3], f[4]


def symbol_kind(full):
    """这只票属于哪一类：'stock' / 'index' / 'fund'；不在产品范围内返回空串。

    按代码段判断，两个源通用。B 股（沪 900xxx / 深 200xxx）、港股、场外基金
    一律不要 —— 之前 GP-B 会混进候选，跟文档里"只支持沪深京 A 股/指数/ETF"对不上。
    """
    mk, code = full[:2], full[2:]
    if len(full) != 8 or not code.isdigit():
        return ""
    if mk == "sh":
        if code.startswith(("60", "68")):
            return "stock"          # 沪市主板 / 科创板
        if code.startswith("000"):
            return "index"          # 上证系列
        if code.startswith(("51", "52", "56", "58")):
            return "fund"           # 沪市 ETF
    elif mk == "sz":
        if code.startswith(("00", "30")):
            return "stock"          # 深市主板 / 创业板
        if code.startswith("399"):
            return "index"          # 深证系列
        if code.startswith(("15", "16", "18")):
            return "fund"           # 深市 ETF / LOF
    elif mk == "bj":
        if code.startswith(("43", "83", "87", "88", "92")):
            return "stock"
        if code.startswith("899"):
            return "index"
    return ""


def _clean_search(recs, limit):
    """两个源的字段位置/分隔符各不相同，各自拆完交给这里统一过滤。"""
    out = []
    for mk, code, name, pinyin, type_ in recs:
        if mk not in ("sh", "sz", "bj"):        # 只留沪深京，过滤港股/美股/场外
            continue
        if not (code.isdigit() and len(code) == 6):
            continue
        if not symbol_kind(mk + code):
            continue
        out.append({"full": mk + code, "code": code, "name": name,
                    "pinyin": pinyin, "type": type_})
    return out[:limit]


# ---------------- 调度 ----------------

PROVIDERS = [TencentProvider(), SinaProvider()]
# 手选源的含义是"**优先**用谁"，不是"只准用谁"：手选的那个源一条都给不出来时
# 仍然会降级到另一个源。刻意保留降级 —— 挂件的作用是看行情，源挂了就什么都不
# 显示，比"换了个源但数据是对的"糟得多。菜单文案因此写"优先"，不写"只用"。
SOURCE_CHOICES = [("auto", "自动（优先主源，挂了换备源）")] + [
    (p.key, "优先" + p.label) for p in PROVIDERS]


class ProviderChain:
    """依次尝试各数据源，谁先给出数据就用谁。"""

    def __init__(self, providers):
        self.providers = list(providers)
        self.last_ok = None        # 上次成功的是谁，下次优先试它

    def order(self, prefer="auto"):
        """本次的尝试顺序：手选优先 > 上次成功 > 注册顺序。"""
        key = prefer if prefer and prefer != "auto" else self.last_ok
        if not key:
            return list(self.providers)
        return ([p for p in self.providers if p.key == key]
                + [p for p in self.providers if p.key != key])

    def call(self, method, *args, prefer="auto", want=None):
        """按优先级调用某个方法。

        want 给了一串 full code 时做**部分补缺**：主源只回来一半，就把缺的那几只
        单独拿去问下一个源，最后按 want 的顺序合并 —— 主源漏掉的那只不会从界面上
        凭空消失。不给 want 就是老行为：谁先给非空结果就用谁的（搜索、分时没有
        "缺一部分"的概念，补缺没意义）。

        单个源挂了不算大事（换下一个），全挂了才把最后一个异常抛出去。
        """
        err = None
        if want is None:
            for p in self.order(prefer):
                try:
                    out = getattr(p, method)(*args)
                except Exception as e:
                    err = e
                    continue
                if out:
                    self.last_ok = p.key
                    return out
            if err is not None:
                raise err
            return None

        want_set = set(want)
        got = {}
        # last_ok 的语义是"下一轮整批行情优先问谁"，所以只有**本轮第一个真正
        # 贡献了数据的源**才有资格改写它。主源回来一半、备源回来空 —— 这种情况
        # 备源没做任何贡献，不能把优先源抢走；只有主源一条都没给时才轮到备源。
        sticky = None
        for p in self.order(prefer):
            missing = [c for c in want if c not in got]
            if not missing:
                break
            before = len(got)
            try:
                out = getattr(p, method)(missing, *args[1:])
            except Exception as e:
                err = e
                continue
            for item in out or []:
                k = item.get("full")
                if k in want_set and k not in got:
                    got[k] = item
            if len(got) > before and sticky is None:
                sticky = p.key
        if sticky is not None:
            self.last_ok = sticky
        if not got and err is not None:
            raise err
        return [got[c] for c in want if c in got]


# 三个入口各用一条链：搜索降级到新浪不该改变下一轮**行情**的源的优先级 ——
# 以前三者共用一个 last_ok，一次搜索失败就能把行情主源带偏。
_QUOTE_CHAIN = ProviderChain(PROVIDERS)
_SEARCH_CHAIN = ProviderChain(PROVIDERS)
_SPARK_CHAIN = ProviderChain(PROVIDERS)


def fetch_quotes(codes, prefer="auto"):
    """抓行情。要哪几只就尽量给全：主源漏了的会拿备源补。

    全部源都失败时抛最后一个异常。
    """
    return _QUOTE_CHAIN.call("quotes", codes, prefer=prefer, want=codes) or []


def search_stocks(keyword, limit=8, prefer="auto"):
    """搜股票。两个源都空才返回 []。

    注意：这跟"谁先给结果就用谁"不一样 —— 某个源**搜不到**不算它成功，
    会继续问下一个源。搜索本来就是各家覆盖不同（腾讯按拼音缩写强、新浪按
    代码强），主源说"没有"不等于真的没有；一个源真的挂了是抛异常，那条路
    才叫降级。以前这里的注释写反了（写着"不会因此去试下一个源"）。
    """
    return _SEARCH_CHAIN.call("search", keyword, limit, prefer=prefer) or []


def fetch_spark(code, prefer="auto"):
    """分时走势。拿不到返回 None（两个源都可能没有分时数据）。"""
    return _SPARK_CHAIN.call("spark", code, prefer=prefer)


def current_source():
    """行情上次实际用的是哪个源（"tencent" / "sina"），还没成功过返回 None。"""
    return _QUOTE_CHAIN.last_ok
