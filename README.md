# Crazy Simple Network Monitoring (CSNM)
Crazy simple network monitoring tool.

Features:
- Simple to setup (needs only a few python librarys)
- No database engine needed, data is stored in files
- Ping Check
- Port Check (with telnet)
- Historic overview (graphic and list)

I didnt really found any simple network monitoring tool so i wrote one with python myself. Im not a programer and my python is a bit rusty but it seem to run nice and smooth so far.
Its running on my Raspberry pi 4 and hardly needs any resources (that was the goal)
Its not ment for productive business monitoring but rather for home lab enverionment.
Overview:
![269239775 14000005_image](https://github.com/silentf666/csnm/assets/19639608/f933154e-2246-4616-8717-e70410fc44f3)
Status History:
![csnm2](https://github.com/silentf666/csnm/assets/19639608/c0118fd9-ca40-45b6-a226-aeeaffbbef4b)

Setup:
- Install python3
- Run "python3 monitoring.py"
- Browse to your http://server-ip:5000
- Consider setting up as a service or put it in autostart.
