import os
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from typing import Optional, Self

@dataclass_json
@dataclass
class YtDlConfig:
    download_dir: Optional[str] = None
    files: Optional[list[str]] = field(default_factory=list)

    @staticmethod
    def get_cfg(path: str) -> Self:
        with open(path, "r", encoding="utf-8") as json_file:
            json_no_comments = os.linesep.join([line for line in json_file.readlines() if not line.strip().startswith("//")])
            result = YtDlConfig.schema().loads(json_no_comments)
            return result