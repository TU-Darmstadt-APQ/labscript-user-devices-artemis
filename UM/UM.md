# UM 1-14-28 for ST
Ultrastable voltage sources. There are 3 primary channels each of them can be rpogrammed with a resoluation of 1 micro Volt. Output range [0.8, 28V].
We use onlz secondary channels A', B', C'

Switching between ultra high precision mode and fast mode is accomplished by software commands.

---
Communication commands

IDN | UM01
DDDD ULTRA XV | ULTRA XV
DDDD FAST XV | FAST XV
DDDD CHXX Y.YYYYYYY | CHXX Y.YYYYYYY

XV
X = H for primary channels (A, B, C) 
X = L for secondary channels (A', B', C')

Y.YYYYYYY
Fast mode: 4 digits after point
Precision mode: 7 digits after point

CHXX
01 - A', fast mode      19 - A', precision mode
03 - B'                 20 - B'
05 - C'                 21 - C'

