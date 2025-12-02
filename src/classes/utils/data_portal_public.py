from typing import Optional

PROD_BASE = "https://nanonet.go.jp/data_service/arim_data.php"
TEST_BASE = "https://dq5rggbsr2dkt.cloudfront.net/test.nanonet.go.jp/data_service/arim_data.php"


def build_public_detail_url(environment: str, code: str, key: str) -> str:
    """Build ARIM Data Portal public detail URL for given environment.
    - production -> nanonet.go.jp
    - test -> CloudFront base with test.nanonet.go.jp path
    Fallback to production pattern if unknown environment.
    """
    base = PROD_BASE if environment == "production" else TEST_BASE if environment == "test" else PROD_BASE
    join = "?mode=detail&code={code}&key={key}"
    return f"{base}{join.format(code=code, key=key)}"
