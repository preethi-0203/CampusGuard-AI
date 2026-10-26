# Weapon Model Verification Report

## 1. Checkpoint Verification
- **Checkpoint Path**: `C:\Users\preet\CampusGuard-AI\backend\ml_models\weapon_detection_trained.pt`
- **File Size**: 5,450,394 bytes
- **SHA-256**: `c78b602ff5c0a1a4c90c2e3853e14f32553e87e860d3878ffe6ed26dbb0ee424`
- **Original `best.pt` Preserved**: `YES (Untouched)`
- **`best.pt` SHA-256**: `07241a8fc57d0f3fd29231dd72b9f452375745290b2185440de0165590997cb5`
- **Class Mapping**: `{0: 'gun', 1: 'knife'}` (Confirmed `{0: 'gun', 1: 'knife'}`)

## 2. Formal Validation Metrics
- **mAP50**: `0.9628`
- **mAP50-95**: `0.5935`
- **Precision**: `0.8725`
- **Recall**: `0.9545`

## 3. Threshold Sensitivity Analysis (20 Validation Images)
| Confidence Threshold | Images with Detections | Correct Class Matches | Match Rate |
|:---:|:---:|:---:|:---:|
| `>= 0.25` | 20/20 | 19/20 | 95.0% |
| `>= 0.50` | 15/20 | 15/20 | 75.0% |
| `>= 0.75` | 3/20 | 3/20 | 15.0% |

## 4. Per-Image Prediction Table
| # | Image | Ground Truth | Detected Class | Top Conf | Conf >= 0.25 | Conf >= 0.50 | Conf >= 0.75 | Visual |
|:---:|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| 1 | `gun_0031.jpg` | **gun** | `gun` | 0.77 | ✅ | ✅ | ✅ | `pred_gun_0031.jpg` |
| 2 | `gun_0032.jpg` | **gun** | `gun` | 0.76 | ✅ | ✅ | ✅ | `pred_gun_0032.jpg` |
| 3 | `gun_0033.jpg` | **gun** | `knife` | 0.33 | ❌ | ❌ | ❌ | `pred_gun_0033.jpg` |
| 4 | `gun_0034.jpg` | **gun** | `gun` | 0.53 | ✅ | ✅ | ❌ | `pred_gun_0034.jpg` |
| 5 | `gun_0035.jpg` | **gun** | `gun` | 0.34 | ✅ | ❌ | ❌ | `pred_gun_0035.jpg` |
| 6 | `gun_0036.jpg` | **gun** | `gun` | 0.56 | ✅ | ✅ | ❌ | `pred_gun_0036.jpg` |
| 7 | `gun_0037.jpg` | **gun** | `gun` | 0.76 | ✅ | ✅ | ✅ | `pred_gun_0037.jpg` |
| 8 | `gun_0038.jpg` | **gun** | `gun` | 0.41 | ✅ | ❌ | ❌ | `pred_gun_0038.jpg` |
| 9 | `gun_0039.jpg` | **gun** | `gun` | 0.65 | ✅ | ✅ | ❌ | `pred_gun_0039.jpg` |
| 10 | `gun_0040.jpg` | **gun** | `gun` | 0.40 | ✅ | ❌ | ❌ | `pred_gun_0040.jpg` |
| 11 | `knife_0031.jpg` | **knife** | `knife` | 0.67 | ✅ | ✅ | ❌ | `pred_knife_0031.jpg` |
| 12 | `knife_0032.jpg` | **knife** | `knife` | 0.66 | ✅ | ✅ | ❌ | `pred_knife_0032.jpg` |
| 13 | `knife_0033.jpg` | **knife** | `knife` | 0.75 | ✅ | ✅ | ❌ | `pred_knife_0033.jpg` |
| 14 | `knife_0034.jpg` | **knife** | `knife` | 0.65 | ✅ | ✅ | ❌ | `pred_knife_0034.jpg` |
| 15 | `knife_0035.jpg` | **knife** | `knife` | 0.66 | ✅ | ✅ | ❌ | `pred_knife_0035.jpg` |
| 16 | `knife_0036.jpg` | **knife** | `knife` | 0.63 | ✅ | ✅ | ❌ | `pred_knife_0036.jpg` |
| 17 | `knife_0037.jpg` | **knife** | `knife` | 0.55 | ✅ | ✅ | ❌ | `pred_knife_0037.jpg` |
| 18 | `knife_0038.jpg` | **knife** | `knife` | 0.64 | ✅ | ✅ | ❌ | `pred_knife_0038.jpg` |
| 19 | `knife_0039.jpg` | **knife** | `knife` | 0.59 | ✅ | ✅ | ❌ | `pred_knife_0039.jpg` |
| 20 | `knife_0040.jpg` | **knife** | `knife` | 0.47 | ✅ | ❌ | ❌ | `pred_knife_0040.jpg` |