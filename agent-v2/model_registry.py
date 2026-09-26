"""Model families shared by discovery and persisted configuration loading."""
import re

ROLE = {
    "CLAUDE": ("anthropic", "opus"),
    "SONNET": ("anthropic", "sonnet"),
    "FABLE": ("anthropic", "fable"),
    "DEEPSEEK": ("deepseek", "flash"),
    "DEEPSEEK_PRO": ("deepseek", "pro"),
    "IMAGE_MODEL": ("openai", "gpt-image"),
}


def version(model: str) -> tuple[int, ...]:
    # Snapshots use either YYYYMMDD, YYYY-MM-DD, or DeepSeek's MMDD suffix.
    name = re.sub(r"-(?:\d{4}-\d{2}-\d{2}|\d{8}|\d{4})$", "", str(model).lower())
    return tuple(int(n) for n in re.findall(r"(?:^|[-.])v?(\d+)(?=[-.]|$)", name))


def in_family(model: str, provider: str, family: str) -> bool:
    if not isinstance(model, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.\-]{2,79}", model):
        return False
    parts = re.split(r"[-.]", model)
    if any(p in parts for p in ("preview", "exp", "beta", "alpha", "latest", "vision", "test", "mini")):
        return False
    if provider == "openai":
        return family == "gpt-image" and bool(re.fullmatch(
            r"gpt-image-\d+(?:[.-]\d+)*(?:-sunburst|-flare)?(?:-\d{4}-\d{2}-\d{2})?", model))
    if provider == "deepseek":
        return bool(re.fullmatch(r"deepseek-(?:v\d+(?:[.-]\d+)*-)?" + re.escape(family)
                                 + r"(?:-\d{4}|-\d{8})?", model))
    if provider == "anthropic":
        return bool(re.fullmatch(r"claude-(?:" + re.escape(family)
            + r"-\d+(?:[.-]\d+)*|\d+(?:[.-]\d+)*-" + re.escape(family)
            + r")(?:-\d{8})?", model))
    return False
