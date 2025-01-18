DEBUG = 1
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