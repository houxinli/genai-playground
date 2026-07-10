import re
from typing import Tuple


def normalize_title(title: str) -> str:
    """去掉尾部括号/版本描述，减少匹配噪音。"""
    t = title.strip()
    t = re.sub(r"\s*[\(\[（【][^\)\]】）]*[\)\]】）]\s*$", "", t)
    t = re.sub(r"\s*-\s*(Live|Remix|Version|Demo|Acoustic).*$", "", t, flags=re.IGNORECASE)
    return t.strip()


def normalize_artists(artists: str) -> str:
    """仅取第一个艺人，避免 feat/合唱干扰。"""
    parts = re.split(r"[\/,&，、\+]", artists)
    return parts[0].strip() if parts else artists.strip()


def make_key(title: str, artists: str) -> str:
    """生成 cache key，使用未清洗的原始文本，避免歧义。"""
    return (title + "|" + artists).strip()


def normalized_query(title: str, artists: str) -> Tuple[str, str]:
    """返回用于查询的规范化标题和艺人。"""
    return normalize_title(title), normalize_artists(artists)


_KANA_OR_HANGUL = re.compile(r"[぀-ヿ가-힯]")
_HAN = re.compile(r"[一-鿿]")


def is_foreign(title: str, artists: str) -> bool:
    """
    中外分流:含假名/谚文视为外文(日语歌名常为纯汉字,靠艺人名里的假名兜底);
    否则含汉字视为中文;纯拉丁视为外文。
    """
    text = f"{title} {artists}"
    if _KANA_OR_HANGUL.search(text):
        return True
    return not _HAN.search(text)
