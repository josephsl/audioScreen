# AudioScreen add-on
# Copyright (C) 2015-2025 NV Access Limited

import os
import collections
import wx
import config
from gui.settingsDialogs import SettingsPanel, NVDASettingsDialog
import gui
import globalPluginHandler
import touchHandler
import globalCommands
import scriptHandler
import api
import ui
from NVDAObjects import NVDAObject
from . import screenBitmap
from . import imagePlayer
# Load 32-bit or 64-bit libaudioverse depending on processor (app) architecture.
if os.environ["PROCESSOR_ARCHITECTURE"] in ("AMD64", "ARM64"):
	from . import libaudioverse64 as libaudioverse
else:
	from . import libaudioverse

class AudioScreenPanel(SettingsPanel):
	# Translators: This is the label for the AudioScreen settings panel.
	title = _("AudioScreen")

	def makeSettings(self,settingsSizer):
		self.plugin = audioScreenPlugin

		generalSizer=wx.StaticBoxSizer(wx.StaticBox(self,wx.ID_ANY,_("General")),wx.VERTICAL)
		modeChoiceSizer=wx.BoxSizer(wx.HORIZONTAL)
		modeChoiceSizer.Add(wx.StaticText(self,wx.ID_ANY,_("Mode")))
		self.modeChoice=wx.Choice(self,wx.ID_ANY,choices=[x[0] for x in self.plugin.audioScreenModes])
		self.modeChoice.SetSelection(self.plugin.curAudioScreenMode)
		modeChoiceSizer.Add(self.modeChoice)
		generalSizer.Add(modeChoiceSizer)
		settingsSizer.Add(generalSizer)
		modesSizer=wx.BoxSizer(wx.HORIZONTAL)
		self.modeControls=[]
		for mode in self.plugin.audioScreenModes[1:]:
			modeSizer=wx.StaticBoxSizer(wx.StaticBox(self,wx.ID_ANY,mode[0]),wx.VERTICAL)
			modeConf=config.conf["audioScreen_%s"%mode[1].__name__]
			for v in mode[2]:
				if v[1]=='boolean':
					control=wx.CheckBox(self,wx.ID_ANY,label=v[3])
					control.SetValue(modeConf[v[0]])
					modeSizer.Add(control)
				else:
					fieldSizer=wx.BoxSizer(wx.HORIZONTAL)
					fieldSizer.Add(wx.StaticText(self,wx.ID_ANY,v[3]))
					control=wx.TextCtrl(self,wx.ID_ANY)
					control.SetValue(str(modeConf[v[0]]))
					fieldSizer.Add(control)
					modeSizer.Add(fieldSizer)
				self.modeControls.append(control)
			modesSizer.Add(modeSizer)
		settingsSizer.Add(modesSizer)

	def onSave(self):
		modeControlIndex=0
		for mode in GlobalPlugin.audioScreenModes[1:]:
			modeConf=config.conf["audioScreen_%s"%mode[1].__name__]
			for v in mode[2]:
				control=self.modeControls[modeControlIndex]
				if v[1]=='boolean':
					modeConf[v[0]]=control.IsChecked()
				else:
					try:
						value=float(control.Value) if v[1]=='float' else int(control.Value)
					except Exception:
						value=v[2]
					modeConf[v[0]]=value
				modeControlIndex+=1
		curMode=self.modeChoice.GetSelection()
		self.plugin.setMode(curMode)


audioScreenPlugin = None


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	# Translators: input gestures category for AudioScreen add-on.
	scriptCategory=_("AudioScreen")

	audioScreenModes=[
		(_("Off"),None),
		(_("pitch stereo grey"),imagePlayer.ImagePlayer_pitchStereoGrey,[
			("reverseBrightness","boolean",False,_("Reverse brightness (useful for white on black)")),
			("width","integer",176,_("Number of columns in stereo field")),
			("height","integer",64,_("Number of rows (frequencies)")),
			("lowFreq","float",500.0,_("Lowest frequency in HZ")),
			("highFreq","float",5000.0,_("highest frequency in HZ")),
			("sweepDelay","float",0.5,_("Initial stereo sweep Delay in seconds")), 
			("sweepDuration","float",4.0,_("Duration of stereo audio sweep in seconds")), 
			("sweepCount","integer",4,_("Numver of stereo sweeps")), 
			("captureWidth","integer",32,_("width (in pixels) of the rectangle at the point under your finger / the mouse")),
			("captureHeight","integer",32,_("height (in pixels) of the rectangle at the point under your finger / the mouse")),
		]),
		(_("HSV Color"),imagePlayer.ImagePlayer_hsv,[
			("width","integer",2,_("Horizontal length of   capture area in pixels")),
			("height","integer",2,_("Vertical length of capture area in pixels")),
			("lowFreq","float",90.0,_("Lowest frequency (blue) in HZ")),
			("highFreq","float",5760,_("highest frequency (red) in HZ")),
		]),
	]
	for mode in audioScreenModes[1:]:
		config.conf.spec["audioScreen_%s"%mode[1].__name__]={v[0]:"%s(default=%s)"%v[1:3] for v in mode[2]}

	def __init__(self):
		super().__init__()
		libaudioverse.initialize()
		self._lastRect=None
		self.curAudioScreenMode=0
		self.imagePlayer=self.screenBitmap=None
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(AudioScreenPanel)
		global audioScreenPlugin
		audioScreenPlugin = self

	def terminate(self):
		libaudioverse.shutdown()
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(AudioScreenPanel)

	def playPoint(self, x: int | None, y: int | None) -> None:
		if not self.imagePlayer:
			return
		screenWidth,screenHeight=api.getDesktopObject().location[2:]
		width=self.captureWidth
		height=self.captureHeight
		x=x-(width/2)
		y=y-(height/2)
		self.playRect(x,y,width,height)

	def playRect(
		self,
		x: int,
		y: int,
		width: int,
		height: int,
		detailed: bool = False,
		forceRestart: bool = False
	) -> None:
		if not self.imagePlayer:
			return
		rect=(x,y,width,height)
		if not forceRestart and rect==self._lastRect:
			return
		self._lastRect=rect
		buffer=self.screenBitmap.captureImage(x,y,width,height)
		self.imagePlayer.setNewImage(buffer,detailed=detailed)

	def stopPlaying(self) -> None:
		if self.imagePlayer:
			self.imagePlayer.setNewImage(None)

	def event_mouseMove(
		self,
		obj: NVDAObject,
		nextHandler: collections.abc.Callable[[], None],
		x: int | None = None,
		y: int | None = None
	):
		nextHandler()
		if touchHandler.handler:
			return
		self.playPoint(x,y)

	def setMode(self, modeID: int, report: bool = False) -> None:
		self.curAudioScreenMode=modeID
		modeInfo=self.audioScreenModes[modeID]
		if self.imagePlayer:
			imagePlayer=self.imagePlayer
			self.imagePlayer=None
			imagePlayer.terminate()
		self.screenBitmap=None
		if modeInfo[1] is None:
			if report:
				ui.message(_("AudioScreen off"))
		else:
			modeConf={k:v for k,v in config.conf["audioScreen_%s"%modeInfo[1].__name__].items()}
			self.captureWidth=modeConf.pop('captureWidth',modeConf['width'])
			self.captureHeight=modeConf.pop('captureHeight',modeConf['height'])
			self.imagePlayer=modeInfo[1](**modeConf)
			self.screenBitmap=screenBitmap.ScreenBitmap(self.imagePlayer.width,self.imagePlayer.height)
			if report:
				inputType=_("touch input") if touchHandler.handler else _("mouse input")
				ui.message(_("AudioScreen mode {mode}, {inputType}").format(mode=modeInfo[0],inputType=inputType))

	@scriptHandler.script(
		# Translators: input help message for AudioScreen add-on command.
		description=_("Toggles AudioScreen   between several modes")
	)
	def script_toggleAudioScreen(self, gesture):
		self.setMode((self.curAudioScreenMode+1)%len(self.audioScreenModes),report=True)

	@scriptHandler.script(
		# Translators: input help message for AudioScreen add-on command.
		description=_("Toggles between light on dark, and dark on light")
	)
	def script_toggleBrightness(self, gesture):
		if not self.imagePlayer:
			ui.message(_("Audioscreen currently off"))
			return
		rb=not self.imagePlayer.reverseBrightness
		if not rb:
			ui.message("Dark on light")
		else:
			ui.message("Light on dark")
		self.imagePlayer.reverseBrightness=rb

	@scriptHandler.script(
		# Translators: input help message for AudioScreen add-on command.
		description=_("Plays the image under your fingers"),
		gestures=[
			"ts:hoverDown", "ts:hold+hoverDown", "ts:hover", "ts:hold+hover", "ts:hold+hoverUp"
		]
	)
	def script_hover(self, gesture):
		preheldTracker=getattr(gesture,'preheldTracker',None)
		if preheldTracker:
			xList=[tracker.x for tracker in preheldTracker.childTrackers]
			xList.append(preheldTracker.x)
			xList.append(gesture.tracker.x)
			yList=[tracker.y for tracker in preheldTracker.childTrackers]
			yList.append(preheldTracker.y)
			yList.append(gesture.tracker.y)
			minX=min(xList)
			maxX=max(xList)
			minY=min(yList)
			maxY=max(yList)
			self.playRect(minX,minY,maxX-minX,maxY-minY,detailed=True)
		else:
			self.playPoint(gesture.tracker.x,gesture.tracker.y)
		script=globalCommands.commands.getScript(gesture)
		if script:
			script(gesture)

	@scriptHandler.script(
		# Translators: input help message for AudioScreen add-on command.
		description=_("Stops audioScreen playback"),
		gesture="ts:hoverUp"
	)
	def script_hoverUp(self, gesture):
		self.stopPlaying()
		script=globalCommands.commands.getScript(gesture)
		if script:
			script(gesture)

	@scriptHandler.script(
		# Translators: input help message for AudioScreen add-on command.
		description=_("Plays the image of the current navigator object"),
		gesture="kb:alt+NVDA+a"
	)
	def script_playNavigatorObject(self, gesture):
		if not self.imagePlayer:
			ui.message(_("AudioScreen disabled"))
			return
		obj=api.getNavigatorObject()
		x,y,w,h=obj.location
		self.playRect(x,y,w,h,detailed=True,forceRestart=True)

	@scriptHandler.script(
		# Translators: input help message for Aduio Screen add-on command.
		description=_("Shows AudioScreen setttings")
	)
	def script_showUI(self, gesture):
		gui.mainFrame.popupSettingsDialog(NVDASettingsDialog, AudioScreenPanel)
