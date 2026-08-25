"""
Deterministic, documented ULPIN scheme for this prototype.

    33            Tamil Nadu state code (fixed)              2 digits
    district      district code                              2 digits
    taluk         taluk code                                 2 digits
    survey_block  cadastral survey block number               4 digits
    floor         floor number within the building            2 digits
    unit          unit number within the floor                2 digits
    --------------------------------------------------------------
    total                                                     14 digits

NOTE ON THE BRIEF: the problem statement lists "taluk(3)" alongside the
other segment widths, but state(2) + district(2) + taluk(3) + block(4) +
floor(2) + unit(2) sums to 15 digits, not the 14 the brief also asks for.
Real ULPIN (Bhu-Aadhaar) is a 14-character alphanumeric ID with its own
internal (non-public) codebook, so there is no authoritative 15- or
14-digit split to defer to either way. To land on exactly 14 digits as
specified, this prototype compresses the taluk segment to 2 digits and
documents the deviation here rather than silently guessing. Every other
segment matches the brief exactly.

This whole scheme is illustrative/synthetic -- it is NOT the real ULPIN
(Bhu-Aadhaar) numbering authority's codebook.
"""

STATE_CODE = "33"  # Tamil Nadu


def generate_ulpin(
    district_code: str,
    taluk_code: str,
    survey_block: str,
    floor_code: str,
    unit_code: str,
) -> str:
    assert len(district_code) == 2
    assert len(taluk_code) == 2
    assert len(survey_block) == 4
    assert len(floor_code) == 2
    assert len(unit_code) == 2
    ulpin = STATE_CODE + district_code + taluk_code + survey_block + floor_code + unit_code
    assert len(ulpin) == 14, f"ULPIN must be 14 digits, got {len(ulpin)}: {ulpin}"
    return ulpin


def format_ulpin(ulpin: str) -> str:
    """Group a raw 14-digit ULPIN for display: SS-DD-TT-BBBB-FF-UU."""
    if len(ulpin) != 14:
        return ulpin
    return f"{ulpin[0:2]}-{ulpin[2:4]}-{ulpin[4:6]}-{ulpin[6:10]}-{ulpin[10:12]}-{ulpin[12:14]}"


def parse_ulpin(ulpin: str) -> dict:
    """Inverse of generate_ulpin -- split a 14-digit ULPIN into its segments."""
    if len(ulpin) != 14 or not ulpin.isdigit():
        raise ValueError(f"Not a valid 14-digit ULPIN: {ulpin!r}")
    return {
        "state_code": ulpin[0:2],
        "district_code": ulpin[2:4],
        "taluk_code": ulpin[4:6],
        "survey_block": ulpin[6:10],
        "floor_code": ulpin[10:12],
        "unit_code": ulpin[12:14],
    }
