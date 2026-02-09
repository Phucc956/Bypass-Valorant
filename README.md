# Gaming Tools: Vanguard Bypass & Garena Auto-Reg

Yo, I've put together (and "refined" a bit) a couple of tools for anyone playing Valorant or needing to mass-create Garena accounts. Feel free to use them if you need 'em. Here's a quick rundown of what's in the box:

---

## 1. SourceBypass.py (Vanguard Bypass for Valorant)

This one is specifically for dealing with Riot's "Vanguard" (VGC) system. If you're running into issues or just want to experiment without dealing with the constant background scans, this is for you.

### What does it do?
- **VGC Management:** Automatically stops and restarts the Vanguard service cleanly—no need to mess around with CMD manually.
- **Pipe Emulation:** Creates a dummy communication pipe to keep Riot's system thinking everything is business as usual.
- **Game Isolation:** Pushes Valorant into a separate "Job Object" to keep it away from certain security scanners.
- **Clean Up:** Scans and terminates suspicious processes that might be trying to sniff out your tools.
- **Modern UI:** Comes with a "pro" lookin' System Monitor, including fake CPU temp and fan RPM graphs (just for show, but it looks legit).

### How to run it:
1. Make sure you have Python installed, then grab these dependencies:
   ```bash
   pip install PyQt6 psutil pywin32
   ```
2. **Important:** You MUST run this as **Administrator** so the tool can touch the system services.
3. Open it up and hit **"Start with Emulate"**. The tool will handle the rest.
