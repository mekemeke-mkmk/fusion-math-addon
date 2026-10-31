# Math Curve 2: macOS Submission Notes

Create this submission by using **Clone** on the approved or pending Windows submission in the Autodesk Design and Make Marketplace Publisher Portal.

## Required Form Values

| Marketplace field | Value |
| --- | --- |
| Version number | `26.2.0` |
| Operating system | macOS |
| Compatible product | Autodesk Fusion only |
| Simulation compatibility | Not selected |
| Distribution / pricing | `30-day trial` |

## Important License Check

Before uploading the Mac archive, confirm the App ID assigned to the cloned macOS submission. The archive currently uses the existing Math Curve 2 Marketplace App ID: `1343581627431012464`.

If the cloned submission receives a different App ID, the `MARKETPLACE_APP_ID` value in `license_manager.py` must be changed to that Mac App ID and the ZIP must be rebuilt before submission. This ensures that the Entitlement API checks the entitlement of the macOS listing, not the Windows listing.

Math Curve requires an internet connection when it verifies the Marketplace entitlement. It does not cache license approvals locally.

## macOS Installation / Uninstallation Text

Installation:
1. Download and run the macOS installer from Autodesk Design and Make Marketplace.
2. Start or restart Autodesk Fusion.
3. In Sketch mode, choose `Create > Math Curve Sketch`.

Uninstallation:
1. Close Autodesk Fusion.
2. Remove Math Curve 2 using the uninstaller provided with the Marketplace installation, or remove the Math Curve 2 bundle from the Autodesk ApplicationPlugins location.
3. Restart Autodesk Fusion if it was running.
