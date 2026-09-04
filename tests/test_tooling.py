from __future__ import annotations

import metiquo


def test_application_package_is_importable() -> None:
    assert metiquo.__name__ == "metiquo"
