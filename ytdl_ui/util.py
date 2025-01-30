import os

DEBUG = 0
def dbg_print(msg):
    if DEBUG:
        print(msg)

def is_blank(s: str | None) -> bool:
    if s is not None:
        return len(s) == 0
    else:
        return True
    
def not_blank(s: str | None) -> bool:
    return not is_blank(s)

def ensure_directory(dir: str):
    if not os.path.exists(dir):
        os.makedirs(dir, exist_ok=True)

def bytes_human_readable(bytes: int) -> str:
    if bytes is None:
        return ""
    elif bytes > 1024**4:
        return f"{float(bytes) / float(1024**4):.3f} TB"
    elif bytes > 1024**3:
        return f"{float(bytes) / float(1024**3):.3f} GB"
    elif bytes > 1024**2:
        return f"{float(bytes) / float(1024**2):.3f} MB"
    elif bytes > 1024**1:
        return f"{float(bytes) / float(1024**1):.3f} KB"
    else:
        return f"{float(bytes) / float(1024**0):.0f} B"

def bytes_per_sec_human_readable(bytes_per_sec: int) -> str:
    if bytes_per_sec is None:
        return ""
    else:
        return f"{bytes_human_readable(bytes_per_sec)}/s"

def seconds_human_readable(seconds: int) -> str:
    if seconds is None:
        return ""
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    days = int(days)
    hours = int(hours)
    minutes = int(minutes)
    seconds = int(seconds)

    if days > 0:
        return f"{days:02}:{hours:02}:{minutes:02}:{seconds:02}"
    elif hours > 0:
        return f"{hours:02}:{minutes:02}:{seconds:02}"
    else:
        return f"{minutes:02}:{seconds:02}"
