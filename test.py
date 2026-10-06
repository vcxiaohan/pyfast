txt = "112233{q}--{w}00"
print(txt.format_map({"q":"*", "w": "[]"}))
print(txt.format(**{"q":"*", "w": "[]"}))
