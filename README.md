> **ここが最新版の編集元です。** 基準リリース: **26.2.0 / hotfix1**。
> フォルダー構成と配布ZIPの場所は [README_最初に読む.md](../../README_最初に読む.md) を参照してください。
> 変更内容は `IMPROVEMENTS.md` に記録してください。

# Fusion Math Add-on

Create mathematical curves inside a Fusion sketch.

## Usage Instructions
1. Install the add-in and start Fusion.
2. Open or create a design, then enter Sketch mode.
3. Start the `Math Curve Sketch` command from `Sketch > Create`.
4. Select an existing sketch line as the baseline.
5. In the `Setup` tab, choose the function unit (for example `1 = 1 mm`), set the x-range, and choose the curves you want to draw.
6. Add functions in the `Library` tab, or pick one from the `Preset Gallery`. Edit the selected function if needed.
7. Check the `Status` box. If a discontinuity or a heavy calculation is found, drawing stops until you review the warning and check `Draw anyway`.
8. Click `Create Curves` to generate the sketch geometry.

## Features
- Supports implicit functions such as `y = f(x)`
- Supports parametric functions such as `x(t), y(t)`, with an option to leave the ends open, close them smoothly, or close them with a straight line
- 3D parametric curves `x(t), y(t), z(t)` (beta); z is drawn along the sketch normal
- Function unit selection (mm, cm, m, in, ft); defaults to the document's length unit
- Preset gallery: waves, catenary, circle, ellipse, rose, heart, involute (gear), cycloid, spirals, helix, and more
- Expression check with readable error messages; `^` can be used for powers
- Discontinuities (such as `tan(x)` or `floor(x)`) are detected and the curve is split at them
- Heavy calculations (too many points or too slow) are stopped before they freeze Fusion
- The function library is saved automatically and restored the next time; it can also be exported and imported as a JSON file

## Function Library Storage
The library is saved on your computer only:
- Windows: `%APPDATA%\MathCurve2\function_library.json`
- macOS: `~/Library/Application Support/MathCurve2/function_library.json`

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
