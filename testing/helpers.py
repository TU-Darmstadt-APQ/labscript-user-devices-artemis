def formate(self, value):
    """Returns value formated like YYYY.YYYY -- 4 digits after and before point
    example: 0.1 --> 0000.1000"""
    return f"{int(value):04d}.{int(round((value % 1) * 10000)):04d}"

print(formate(None, 7.1242))
print(formate(None, 0.1))
print(formate(None, 0000.1000))
print(formate(None, 4042.1424))