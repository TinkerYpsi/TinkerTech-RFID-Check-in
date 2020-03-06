#!/user/bin/env python

import urllib.request

url = 'http://www.tinkertech.io/IoT/users.txt'
data = urllib.request.urlopen(url)
for line in data:
	print(line.decode('utf-8').strip())
