"""Mock DigiLocker document catalogue used during Phase I development."""

MOCK_DOCUMENTS = [
    {
        "doc_type": "aadhaar",
        "issuer": "UIDAI",
        "issue_date": "2019-05-12",
        "data": {
            "aadhaar_verified": True,
        },
    },
    {
        "doc_type": "degree",
        "issuer": "IIT Guwahati",
        "issue_date": "2018-07-01",
        "data": {
            "qualification": "B.Tech Civil Engineering",
            "percentage": 78.5,
            "year_of_passing": 2018,
        },
    },
    {
        "doc_type": "marksheet",
        "issuer": "IIT Guwahati",
        "issue_date": "2018-06-15",
        "data": {
            "cgpa": 8.1,
            "class": "Distinction",
        },
    },
    {
        "doc_type": "experience",
        "issuer": "North Eastern Electric Power Corporation Ltd",
        "issue_date": "2024-03-31",
        "data": {
            "role": "Assistant Engineer",
            "years_experience": 6,
            "organization": "NEEPCO",
        },
    },
]
