import re

# Split on: backslash, forward slash, semicolon, comma, CR, LF
SPLIT_REGEX = re.compile(r"[\\/;,\r\n ]+")
CAS_REGEX = re.compile(r"^\d{2,7}-\d{2}-\d$")

# YYYY-MM-DD optionally followed by time
YMD_TIME_REGEX = re.compile(r"^(\d{2,7})-(\d{2})-(\d{2})(?:\s+\d{2}:\d{2}:\d{2})?$")

# Slash date optionally followed by time: 10/06/2442 or 10/06/2442 00:00:00
SLASH_TIME_REGEX = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2,7})(?:\s+\d{2}:\d{2}:\d{2})?$")


def build_adj_digit_map() -> dict[str, set[str]]:
    """
    Adjacency mapping combining:
      - keyboard number row adjacency (left/right)
      - numpad orthogonal adjacency
    """
    # Keyboard number row adjacency (left/right)
    row_adj = {
        "0": {"9"},
        "1": {"2"},
        "2": {"1", "3"},
        "3": {"2", "4"},
        "4": {"3", "5"},
        "5": {"4", "6"},
        "6": {"5", "7"},
        "7": {"6", "8"},
        "8": {"7", "9"},
        "9": {"8", "0"},
    }

    # Numpad orthogonal adjacency
    # 7 8 9
    # 4 5 6
    # 1 2 3
    #   0
    num_adj = {
        "7": {"8", "4"},
        "8": {"7", "9", "5"},
        "9": {"8", "6"},
        "4": {"7", "5", "1"},
        "5": {"8", "4", "6", "2"},
        "6": {"9", "5", "3"},
        "1": {"4", "2"},
        "2": {"1", "3", "5", "0"},
        "3": {"2", "6"},
        "0": {"2"},
    }

    out = {str(d): set() for d in range(10)}
    for d in out:
        out[d] |= row_adj.get(d, set())
        out[d] |= num_adj.get(d, set())
    return out


ADJ_DIGITS = build_adj_digit_map()