"use strict";

const { contextBridge, ipcRenderer } = require("electron");

function subscribe(channel, callback) {
  if (typeof callback !== "function") return () => {};
  const listener = (_event, payload) => callback(payload);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
}

contextBridge.exposeInMainWorld("jack", Object.freeze({
  state: () => ipcRenderer.invoke("jack:state"),
  install: () => ipcRenderer.invoke("jack:install"),
  uninstall: () => ipcRenderer.invoke("jack:uninstall"),
  restartCodex: () => ipcRenderer.invoke("jack:restartCodex"),
  listSkills: () => ipcRenderer.invoke("jack:listSkills"),
  saveSkills: (disabled) => ipcRenderer.invoke("jack:saveSkills", disabled),
  setAutoInstall: (value) => ipcRenderer.invoke("jack:setAutoInstall", value === true),
  quit: () => ipcRenderer.invoke("jack:quit"),
  win: (action) => ipcRenderer.invoke("jack:win", action),
  onLog: (callback) => subscribe("jack:log", callback),
  onStatus: (callback) => subscribe("jack:status", callback),
  onNotify: (callback) => subscribe("jack:notify", callback),
}));
