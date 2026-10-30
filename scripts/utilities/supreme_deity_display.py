"""Temporary display settings with a durable, verified restoration record.

Resolution uses documented Win32 APIs. Per-monitor scaling uses the Windows
Settings private -3/-4 display packets; unsupported/custom configurations fail
closed before changing resolution. No display writes occur on import.
"""
import ctypes as c
import json
import time
from pathlib import Path

DISPLAY_RESOLUTIONS=((2560,1440),(1920,1080))
SCALES=(100,125,150,175,200,225,250,300,350,400,450,500)
def display_matches(actual,expected):
    # Driver flags/fixed-output policy may normalize when the mode changes.
    keys=('PelsWidth','PelsHeight','BitsPerPel','DisplayOrientation','Position_x','Position_y')
    return (actual['device']==expected['device'] and actual['scale']==expected['scale']
            and all(actual['mode'][k]==expected['mode'][k] for k in keys)
            and abs(actual['mode']['DisplayFrequency']-expected['mode']['DisplayFrequency'])<=1)

def scale_relative(packet,actual,target):
    # Anchor the relative step to the independently measured current percentage.
    if actual not in SCALES or target not in SCALES:
        raise OSError('Exact monitor scaling is unsupported.')
    relative=packet.current+SCALES.index(target)-SCALES.index(actual)
    if not packet.minimum<=relative<=packet.maximum:
        raise OSError('Saved/requested scale is unavailable on this monitor.')
    return relative

MODE_KEYS=('PelsWidth','PelsHeight','DisplayFrequency','BitsPerPel','DisplayOrientation',
           'DisplayFlags','DisplayFixedOutput','Position_x','Position_y')
class Luid(c.Structure):
    _fields_=[('low',c.c_uint32),('high',c.c_int32)]
class Header(c.Structure):
    _fields_=[('kind',c.c_uint32),('size',c.c_uint32),('adapter',Luid),('source',c.c_uint32)]
class ScaleGet(c.Structure):
    _fields_=[('header',Header),('minimum',c.c_int32),('current',c.c_int32),('maximum',c.c_int32)]
class ScaleSet(c.Structure):
    _fields_=[('header',Header),('relative',c.c_int32)]
class OpenAdapter(c.Structure):
    _fields_=[('device',c.c_wchar*32),('handle',c.c_uint32),('adapter',Luid),('source',c.c_uint32)]
class CloseAdapter(c.Structure):
    _fields_=[('handle',c.c_uint32)]

class WindowsDisplay:
    def __init__(self,device):
        import win32api,win32con
        self.api,self.con,self.device=win32api,win32con,device
        self.user=c.WinDLL('user32')
        self.gdi=c.WinDLL('gdi32')
    @classmethod
    def for_game(cls):
        from utilities.capture_window import find_game_window
        import win32api
        hwnd=find_game_window()
        if not hwnd:raise OSError('Open the game before setting its display.')
        monitor=win32api.MonitorFromWindow(hwnd,2)
        return cls(win32api.GetMonitorInfo(monitor)['Device'])
    def _scale_packet(self):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Control Panel\Desktop') as key:
            try:custom=winreg.QueryValueEx(key,'Win8DpiScaling')[0]
            except FileNotFoundError:custom=0
        if custom:raise OSError('Custom Windows scaling is active; exact automatic restoration is unavailable.')
        request=OpenAdapter();request.device=self.device
        code=self.gdi.D3DKMTOpenAdapterFromGdiDisplayName(c.byref(request))
        if code:raise OSError(f'Cannot identify display adapter ({code}).')
        try:
            packet=ScaleGet(Header(0xfffffffd,c.sizeof(ScaleGet),request.adapter,request.source))
            code=self.user.DisplayConfigGetDeviceInfo(c.byref(packet))
            if code:raise OSError(f'Windows cannot read restorable scaling ({code}).')
            if not packet.minimum<=packet.current<=packet.maximum:
                raise OSError('Windows returned an unsupported scaling range.')
            return packet
        finally:
            self.gdi.D3DKMTCloseAdapter(c.byref(CloseAdapter(request.handle)))
    def actual_scale(self):
        # Documented, independent monitor-scale query; never infer from minimum.
        shcore=c.WinDLL('shcore')
        get_scale=shcore.GetScaleFactorForMonitor
        get_scale.argtypes=[c.c_void_p,c.POINTER(c.c_int)]
        get_scale.restype=c.c_long
        for monitor,_,_ in self.api.EnumDisplayMonitors():
            if self.api.GetMonitorInfo(monitor)['Device']==self.device:
                value=c.c_int()
                code=get_scale(int(monitor),c.byref(value))
                if code or value.value not in SCALES:
                    raise OSError(f'Cannot verify exact monitor scale ({code}, {value.value}%).')
                return value.value
        raise OSError('Saved display monitor is unavailable.')

    def settled_scale(self):
        previous=None;matches=0
        for _ in range(30):
            packet=self._scale_packet();actual=self.actual_scale()
            signature=(packet.minimum,packet.current,packet.maximum,actual)
            matches=matches+1 if signature==previous else 1
            if matches>=4:return packet,actual
            previous=signature
            time.sleep(.2)
        raise OSError('Windows scaling did not settle after resolution change.')

    def read(self):
        mode=self.api.EnumDisplaySettings(self.device,self.con.ENUM_CURRENT_SETTINGS)
        return dict(device=self.device,mode={k:getattr(mode,k) for k in MODE_KEYS},
                    scale=self.actual_scale())
    def preflight(self,resolution=(2560,1440)):
        packet=self._scale_packet()
        scale_relative(packet,self.actual_scale(),125)
        mode=self.api.EnumDisplaySettings(self.device,self.con.ENUM_CURRENT_SETTINGS)
        if (mode.PelsWidth,mode.PelsHeight)==resolution:return
        mode.PelsWidth,mode.PelsHeight=resolution
        mode.Fields=self.con.DM_PELSWIDTH|self.con.DM_PELSHEIGHT
        if self.api.ChangeDisplaySettingsEx(self.device,mode,self.con.CDS_TEST)!=0:
            raise OSError(f'{resolution[0]} × {resolution[1]} is unsupported at the current refresh rate.')
    def apply(self,settings):
        current=self.read()
        mode=self.api.EnumDisplaySettings(self.device,self.con.ENUM_CURRENT_SETTINGS)
        for key,value in settings['mode'].items():setattr(mode,key,value)
        mode.Fields=(self.con.DM_PELSWIDTH|self.con.DM_PELSHEIGHT|self.con.DM_DISPLAYFREQUENCY|
                     self.con.DM_BITSPERPEL|self.con.DM_DISPLAYORIENTATION|self.con.DM_DISPLAYFLAGS|
                     self.con.DM_DISPLAYFIXEDOUTPUT|self.con.DM_POSITION)
        if current["mode"]!=settings["mode"]:
            code=self.api.ChangeDisplaySettingsEx(self.device,mode,0)
            if code:raise OSError(f'Resolution change failed ({code}).')
        packet,actual=self.settled_scale()
        relative=scale_relative(packet,actual,settings["scale"])
        request=ScaleSet(Header(0xfffffffc,c.sizeof(ScaleSet),packet.header.adapter,packet.header.source),relative)
        if relative!=packet.current:
            code=self.user.DisplayConfigSetDeviceInfo(c.byref(request))
            if code:raise OSError(f'Scaling change failed ({code}).')
        matches=0
        for _ in range(30):
            observed=self.read()
            matches=matches+1 if display_matches(observed,settings) else 0
            if matches>=4:return
            time.sleep(.2)
        raise OSError(f'Windows did not confirm display settings. Requested {settings}; observed {observed}.')

class DisplaySession:
    def __init__(self,path,backend=None):
        self.path=Path(path)
        self.backend=backend
    @property
    def saved(self):return self.path.is_file()
    def _load(self):
        data=json.loads(self.path.read_text(encoding='utf-8'))
        if (set(data)!= {'device','mode','scale'} or set(data['mode'])!=set(MODE_KEYS)
                or not isinstance(data['device'],str) or data['scale'] not in SCALES
                or any(type(v) is not int for v in data['mode'].values())):
            raise OSError('Display recovery file is invalid; it has been retained.')
        return data
    def set_display(self,resolution=(2560,1440)):
        if resolution not in DISPLAY_RESOLUTIONS:raise OSError("Unsupported display preset.")
        if self.saved:raise OSError('Original settings are already saved. Use Restore display first.')
        backend=self.backend or WindowsDisplay.for_game()
        original=backend.read()
        backend.preflight(resolution)
        target=json.loads(json.dumps(original))
        target['mode'].update(PelsWidth=resolution[0],PelsHeight=resolution[1])
        target['scale']=125
        self.path.parent.mkdir(parents=True,exist_ok=True)
        # Exclusive creation prevents overwriting a previous recovery record.
        with self.path.open('x',encoding='utf-8') as stream:
            json.dump(original,stream,indent=2)
            stream.flush()
            import os
            os.fsync(stream.fileno())
        try:
            backend.apply(target)
            if not display_matches(backend.read(),target):raise OSError('Target display settings were not verified.')
        except Exception as exc:
            try:
                backend.apply(original)
                if not display_matches(backend.read(),original):raise OSError('Restoration could not be verified.')
                self.path.unlink()
            except Exception as restore_error:
                raise OSError(f'{exc} Restore failed: {restore_error}. Saved settings retained.') from exc
            raise OSError(f'{exc} Original settings restored.') from exc
        return target
    def restore(self):
        if not self.saved:return False
        original=self._load()
        backend=self.backend or WindowsDisplay(original['device'])
        backend.apply(original)
        if not display_matches(backend.read(),original):raise OSError('Restoration unverified; saved settings retained.')
        self.path.unlink()
        return True
