import re


def tokenize(text: str) -> list[str]:
    normalized = text.lower()
    words = re.findall(r"[a-z]+(?:[-_]\w+)*|\d+(?:\.\d+)*", normalized)
    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", normalized)
    chinese: list[str] = []
    for run in chinese_runs:
        chinese.extend(run if len(run) == 1 else (run[i : i + 2] for i in range(len(run) - 1)))
    return [*words, *chinese]
