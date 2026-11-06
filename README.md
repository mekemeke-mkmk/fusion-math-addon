> **ここが最新版の編集元です。** 基準リリース: **26.2.0 / hotfix1**。
> フォルダー構成と配布ZIPの場所は [README_最初に読む.md](../../README_最初に読む.md) を参照してください。
> 変更内容は `IMPROVEMENTS.md` に記録してください。

# Fusion Math Add-on

Create mathematical curves inside a Fusion sketch.

## Usage Instructions
1. Install Math Curve 2 and start Autodesk Fusion.
2. Open or create a design and enter Sketch mode.
3. In the Sketch workspace, choose `Create > Math Curve Sketch`. The Math Curve window opens.
4. Add functions with `+ Add function...` (a new `y = f(x)`, `x(t), y(t)`, or 3D function, or a preset). Select a function to edit its expressions and variables; the graph updates as you type or drag a variable slider.
5. Check `Draw` for the functions to create. Use `InvO`, `InvX`, and `InvY` to flip a function on its baseline.
6. Under `Place in sketch`, click `Select line` and pick an existing sketch line (its start point is the origin and its direction is +x), or click `Sketch origin`. Choose the unit and the x range for `y = f(x)`. The curves are previewed in the Fusion viewport.
7. Check `Status`. If a discontinuity or a heavy calculation is found, review it and check `Draw anyway` to continue.
8. Click `Create Curves` to generate the curves in the sketch.

## Features
- Supports implicit functions such as `y = f(x)`
- Supports parametric functions such as `x(t), y(t)`, with an option to leave the ends open, close them smoothly, or close them with a straight line
- 3D parametric curves `x(t), y(t), z(t)` (beta); z is drawn along the sketch normal
- Function unit selection (mm, cm, m, in, ft); defaults to the document's length unit
- Preset gallery: waves, catenary, circle, ellipse, rose, heart, involute (gear), cycloid, spirals, helix, and more
- Expression check with readable error messages; `^` can be used for powers
- Discontinuities (such as `tan(x)` or `floor(x)`) are detected and the curve is split at them
- Heavy calculations (too many points or too slow) are stopped before they freeze Fusion
- Output Curve: `Light curve` (default) creates one fixed spline per curve that passes through every sample point without adding sketch points, so the sketch stays fast. `Editable fit-point spline` creates the traditional spline with one fit point per sample, which can be edited but makes later operations slower.
- The function library is saved automatically and restored the next time; it can also be exported and imported as a JSON file

## The Math Curve Window
Everything happens in one window, opened with `Math Curve Sketch`:
- Left: the function list with the `Draw`, `InvO`, `InvX`, `InvY` checkboxes, and the editor of the selected function (name, type, expressions, step or t range, start/end connection, variables with sliders and min / max). `More` exports, imports, or reloads the library.
- Right: the graph (drag to pan, scroll or `+` / `−` to zoom, `Fit`, `Origin`; the shaded band is the x range used for `y = f(x)`), and below it `Place in sketch` and `Status` with `Create Curves`.
- The preview on the baseline is drawn as display-only graphics in the Fusion viewport, so it never changes the sketch and stays fast. `Create Curves` adds the curves to the baseline's sketch as one undoable step.
- The graph uses the same calculation as the sketch, including discontinuity splitting and error messages. 3D curves are shown as their x-y view; `InvO` / `InvX` / `InvY` apply only to the placement in the sketch.

## Function Library Storage
The library is saved on your computer only:
- Windows: `%APPDATA%\MathCurve2\function_library.json`
- macOS: `~/Library/Application Support/MathCurve2/function_library.json`

## Developer Testing (license check)
On the developer's own PC, the Marketplace license check can be skipped while testing the edit source. Use either method:
- Flag file (recommended, no restart of Windows needed). In PowerShell:
  `New-Item -ItemType File -Force "$env:APPDATA\MathCurve2\developer_mode"`
- Environment variable: `setx MATH_CURVE_DEV_MODE 1`, then quit Fusion completely and start it again.

The `Status` box in the Setup tab shows `[DEV] Developer mode` while it is active. If the license message still appears, it also shows the add-in folder and the developer-mode state to help find the cause.

Developer mode is ignored when the add-in runs from the Marketplace install folder (`ApplicationPlugins`), so installed copies always check the license. To turn it off, delete the flag file and/or run `setx MATH_CURVE_DEV_MODE 0`.

## Marketplace Submission Notes
- Version: `26.2.0` in both the Marketplace form and the Fusion manifest.
- License model: Autodesk Marketplace 30-day trial, followed by Marketplace entitlement.
- Trial behavior: The trial has the same features as the paid version.
- Entitlement API: Fusion sends its signed-in Autodesk user ID and this app's Marketplace ID to Autodesk's official `checkentitlement` endpoint. The add-in allows curve creation only when the response returns `IsValid: true`.
- Offline behavior: An active internet connection is required when Math Curve verifies the Marketplace entitlement. The add-in does not cache license approvals locally.
- Simulation compatibility: Not supported; do not select Simulation in the compatible products list.
- Platform: Windows only. Do not select macOS until a separately tested Mac submission is made.

## License / Privacy
This app runs locally and does not collect or share project data. Your function library is stored only on your computer (see above).
For license verification only, it sends the signed-in Autodesk user ID and the Marketplace app ID directly to Autodesk's Marketplace entitlement service. No data is sent to the publisher or any other third party.

## Contact
mekemeke.lab@gmail.com

## Development Rule
Any code or document change in this repository must be recorded in `IMPROVEMENTS.md`.
