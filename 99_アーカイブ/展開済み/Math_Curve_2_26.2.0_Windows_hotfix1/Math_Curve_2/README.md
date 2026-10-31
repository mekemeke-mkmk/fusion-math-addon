# Fusion Math Add-on

Create mathematical curves inside a Fusion sketch.

## Usage Instructions
1. Install the add-in and start Fusion.
2. Open or create a design, then enter Sketch mode.
3. Start the `Math Curve Sketch` command from `Sketch > Create`.
4. Select an existing sketch line as the baseline.
5. Set the x-range and choose the curves you want to draw.
6. Edit or save functions in the `Library` tab if needed.
7. Click `Create Curves` to generate the sketch geometry.

## Features
- Supports implicit functions such as `y = f(x)`
- Supports parametric functions such as `x(t), y(t)`
- Lets you reuse saved functions and edit variables

## Marketplace Submission Notes
- Version: `26.2.0` in both the Marketplace form and the Fusion manifest.
- License model: Autodesk Marketplace 30-day trial, followed by Marketplace entitlement.
- Trial behavior: The trial has the same features as the paid version.
- Entitlement API: Fusion sends its signed-in Autodesk user ID and this app's Marketplace ID to Autodesk's official `checkentitlement` endpoint. The add-in allows curve creation only when the response returns `IsValid: true`.
- Offline behavior: An active internet connection is required when Math Curve verifies the Marketplace entitlement. The add-in does not cache license approvals locally.
- Simulation compatibility: Not supported; do not select Simulation in the compatible products list.
- Platform: Windows only. Do not select macOS until a separately tested Mac submission is made.

## License / Privacy
This app runs locally and does not collect, store, or share project data.
For license verification only, it sends the signed-in Autodesk user ID and the Marketplace app ID directly to Autodesk's Marketplace entitlement service. No data is sent to the publisher or any other third party.

## Contact
mekemeke.lab@gmail.com

## Development Rule
Any code or document change in this repository must be recorded in `IMPROVEMENTS.md`.
