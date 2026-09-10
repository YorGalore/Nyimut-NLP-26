import requests

url = "https://api.gdeltproject.org/api/v2/doc/doc"
p = {"query": "sanctions sourcelang:english",
     "mode": "ArtList", "format": "json", "maxrecords": 10,
     "startdatetime": "20211001000000", "enddatetime": "20211002000000"}

r = requests.get(url, params=p, headers={"User-Agent": "riset-kampus"})
print(r.status_code, r.text[:500])