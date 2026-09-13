from gfw_anomaly.validation import _iter_self_reported_ids


def test_extract_gfw_identity_ids():
    payload = {
        "entries": [
            {
                "selfReportedInfo": [
                    {
                        "id": "gfw-1",
                        "shipname": "KNOWN SHIP",
                        "imo": "1234567",
                        "ssvid": "111222333",
                        "flag": "AAA",
                    }
                ]
            }
        ]
    }
    rows = _iter_self_reported_ids(payload)
    assert rows == [
        {
            "vessel_id": "gfw-1",
            "ship_name": "KNOWN SHIP",
            "imo": "1234567",
            "mmsi": "111222333",
            "flag": "AAA",
            "from": None,
            "to": None,
        }
    ]
