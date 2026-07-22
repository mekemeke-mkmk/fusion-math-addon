# Fusion Math Add-on

This add-in allows you to generate advanced mathematical curves directly in Autodesk Fusion sketches.

## Features
- Supports mathematical functions
- Parametric curves
- High precision curve generation

## Requirements
- Autodesk Fusion
- A sketch must be open or being edited before you run the add-in

## How to Use
1. Start Autodesk Fusion.
2. Open a design that contains a sketch, or create a new sketch.
3. Open the Sketch workspace and go to the Create area.
4. Click `Math Curve Sketch`.
5. In the Placement tab, select one sketch line to define the curve origin and direction.
6. In the Setup tab, choose the function you want to draw and set the drawing range.
7. In the Library tab, edit the selected function if needed.
8. Click `Create Curves` to generate the sketch curve.

## Trial and License
This add-in currently does not implement a trial license flow in the codebase.

The repository does not contain an Autodesk Entitlement API integration yet, so there is no in-app license validation, trial activation, or entitlement check at the moment.

If the marketplace submission requires a 30-day trial, that licensing flow will need to be added separately before release.

## Marketplace Notes
- The add-in is intended for Autodesk Fusion, not Revit.
- The add-in UI is registered for the sketch Create area.
- Supported OS settings should match the marketplace submission settings.

## Privacy Policy
This app does not collect, store, or share any personal data.

The app runs locally and does not send any data externally.

## Contact
mekemeke.lab@gmail.com


# 開発ルール

このリポジトリではすべての変更に対して
IMPROVEMENTS.mdへ必ず記録すること。

記録なしの変更は禁止。
