"""Read-only privilege preflight for SD input (no elevation or input here)."""


def input_access_error():
    import win32api
    import win32con
    import win32gui
    import win32process
    import win32security
    from utilities.capture_window import find_game_window

    hwnd = find_game_window()
    if not hwnd:
        return "Open the configured 7DS game window first."
    if win32gui.IsIconic(hwnd):
        return "Restore the minimized game window first."

    def elevated(pid):
        process = win32api.OpenProcess(0x1000, False, pid)
        try:
            token = win32security.OpenProcessToken(process, win32con.TOKEN_QUERY)
            try:
                return bool(win32security.GetTokenInformation(token, win32security.TokenElevation))
            finally:
                token.Close()
        finally:
            process.Close()

    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if elevated(pid) and not elevated(win32api.GetCurrentProcessId()):
            return ("7DS is running as administrator, but this launcher is not. "
                    "Use 'Restart as administrator' in the GUI, approve Windows UAC, then Start live.")
    except Exception as exc:
        return f"Cannot verify game input privileges: {exc}. Try Restart as administrator."
    return None
