/* Original repair illustrations, sharing the hardware family and its 24px grid. */
const FIX_ART = {
  "net.restart": HW_ART.network + "<g class=\"fix-action\"><circle cx=\"18\" cy=\"18\" r=\"5\" fill=\"var(--panel)\"/><path d=\"M16 17a2.5 2.5 0 1 1 0 3m0-5v2h2\"/></g>",
  "net.flush": "<path d=\"M5 4h10v5H5zm-1 9h8m-8 4h5m7-5 4 4-4 4m-4-4h8\"/>",
  "gpu.restart": HW_ART.gpu + "<g class=\"fix-action\"><circle cx=\"18\" cy=\"18\" r=\"5\" fill=\"var(--panel)\"/><path d=\"M16 17a2.5 2.5 0 1 1 0 3m0-5v2h2\"/></g>",
  "device.restart": HW_ART.mouse + "<g class=\"fix-action\"><circle cx=\"18\" cy=\"18\" r=\"5\" fill=\"var(--panel)\"/><path d=\"M16 17a2.5 2.5 0 1 1 0 3m0-5v2h2\"/></g>",
  "sound.apps": HW_ART.headset,
  "sound.restart": "<path d=\"m9 5-5 4H2v6h2l5 4zM13 9a5 5 0 0 1 0 6m4-9a9 9 0 0 1 0 12\"/>" + "<g class=\"fix-action\"><circle cx=\"18\" cy=\"18\" r=\"5\" fill=\"var(--panel)\"/><path d=\"M16 17a2.5 2.5 0 1 1 0 3m0-5v2h2\"/></g>",
  "display.restore": HW_ART.display + "<g class=\"fix-action\"><circle cx=\"18\" cy=\"18\" r=\"5\" fill=\"var(--panel)\"/><path d=\"M16 17a2.5 2.5 0 1 1 0 3m0-5v2h2\"/></g>",
  "steam.restart": "<circle cx=\"16\" cy=\"7\" r=\"4\"/><circle cx=\"6\" cy=\"17\" r=\"3\"/><path d=\"m8 15 5-6m-5 9 7-7M2 12l2 2\"/>" + "<g class=\"fix-action\"><circle cx=\"18\" cy=\"18\" r=\"5\" fill=\"var(--panel)\"/><path d=\"M16 17a2.5 2.5 0 1 1 0 3m0-5v2h2\"/></g>",
  "shader.clear": "<path d=\"m12 3 9 5-9 5-9-5zm-9 9 9 5 9-5M3 16l9 5 9-5\"/>",
  "steam.zombie": "<rect x=\"3\" y=\"4\" width=\"18\" height=\"16\" rx=\"2\"/><path d=\"M3 8h18m-13 4 8 5m0-5-8 5\"/>",
  "steam.verify": "<path d=\"M5 3h9l5 5v13H5zM14 3v5h5m-11 7 3 3 5-6\"/>",
  "mic.privacy": HW_ART.mic + "<path d=\"m17 14 5 2v3l-3 3-3-3v-3z\"/>",
  "startup.apps": "<rect x=\"3\" y=\"5\" width=\"18\" height=\"15\" rx=\"2\"/><path d=\"M3 9h18m-9 8v-5m-3 3 3-3 3 3\"/>",
  "defender.exclude": "<path d=\"m12 3 8 3v6c0 4-4 7-8 9-4-2-8-5-8-9V6zm-4 9h8\"/>",
  "fullscreen.exclusive": "<path d=\"M3 8V3h5m8 0h5v5M3 16v5h5m8 0h5v-5\"/><rect x=\"7\" y=\"7\" width=\"10\" height=\"10\" rx=\"1\"/>",
  "power.performance": HW_ART.power,
};
