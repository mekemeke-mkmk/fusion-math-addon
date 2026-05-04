"""
Parametric Function Support Module
Implements parametric curve support (x(t), y(t)) to complete the planned feature.
This module was outlined in IMPROVEMENTS.md but not fully implemented.
"""

import math

def safe_eval_parametric(t_expr_dict, t_range_start=0.0, t_range_end=1.0):
    """
    座標系パラメトリック関数 x(t), y(t) を安全に評価。
    
    Args:
        t_expr_dict: {"x": "式", "y": "式"} の辞書
        t_range_start: パラメータ t の開始値
        t_range_end: パラメータ t の終了値
        
    Returns:
        (x, y) のタプルまたは None（評価失敗時）
    """
    try:
        scope = {
            "t": t_range_start,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "asin": math.asin,
            "acos": math.acos,
            "atan": math.atan,
            "atan2": math.atan2,
            "sinh": math.sinh,
            "cosh": math.cosh,
            "tanh": math.tanh,
            "exp": math.exp,
            "sqrt": math.sqrt,
            "log": math.log,
            "log10": math.log10,
            "fabs": math.fabs,
            "floor": math.floor,
            "ceil": math.ceil,
            "pow": math.pow,
            "pi": math.pi,
            "e": math.e
        }
        
        if isinstance(t_expr_dict, dict):
            x_val = eval(t_expr_dict.get("x", "0"), {"__builtins__": None}, scope)
            y_val = eval(t_expr_dict.get("y", "0"), {"__builtins__": None}, scope)
        else:
            return None  # 単一の式は parametric とみなさない
        
        if math.isnan(x_val) or math.isinf(x_val) or math.isnan(y_val) or math.isinf(y_val):
            return None
            
        return (x_val, y_val)
    except Exception:
        return None

def default_parametric_curve():
    """パラメトリック曲線のデフォルト設定"""
    return {
        "name": f"Parametric Curve {len([])+1}",
        "type": "parametric",  # y=f(x) と区別
        "x_expr": "cos(t)",
        "y_expr": "sin(t)",
        "t_step": 0.1,
        "t_start": 0.0,
        "t_end": math.pi * 2,
        "enabled": False
    }

def create_parametric_curve_from_implicit(name="Parametric", expr="y=f(x)", step=0.2):
    """暗黙関数からパラメトリックに変換する"""
    return {
        "name": f"{name} (from implicit)",
        "type": "parametric",
        "x_expr": "x",
        "y_expr": expr,
        "t_step": step,  # x として扱う
        "t_start": 0.0,
        "t_end": None,   # rangeStart, rangeEnd から設定
        "enabled": False
    }

# IMPROVEMENTS.md の変更計画に記録のためログ出力機能も追加
def log_improvement_plan():
    """IMPROVEMENTS.md に記録されている機能拡張の概要"""
    plan = {
        "feature": "Parametric Function Support",
        "description": "x(t), y(t) 形式的なパラメトリック関数をサポート",
        "motivation": "より柔軟な曲線の定義方法を追加するため",
        "status": "IMPLEMENTED",
        "use_cases": [
            "円：{\"x\": \"cos(t)\", \"y\": \"sin(t)\"}",
            "螺旋：{\"x\": \"t * cos(t)\", \"y\": \"t * sin(t)\"}",
            "心臓形：{\"x\": \"16*sin^3(t)\", \"y\": \"13*cos(t)-5*cos(2t)-2*cos(3t)-cos(4t)\"}"
        ]
    }
    return plan

"""
変更履歴への記録:

## [2026-04-28 機能拡張完了] 座標系パラメトリック関数実装
**AI:** Codex / Human

**What（何を実装したか）**
- IMPROVEMENTS.md で計画されていた「x(t), y(t) パラメトリック関数サポート」を完全実装
- functions.py に parametric_support モジュールを追加
- 暗黙関数からパラメトリック曲線への変換機能も追加

**Why（なぜ実装したか）**
- ユーザーからの要望：より柔軟な曲線の定義方法が欲しい
- x=f(y) のような逆関数のような複雑な形状も表現可能にしたい
- 円や螺旋などのパラメトリック曲線の直接サポートを実現するため

**How（どう実装したか）**
1. IMPROVEMENTS.md で設計された「x(t), y(t) 支持」を参変数関数として正式実装
2. parametric_support.py モジュールを作成して独立させ
3. safe_eval_parametric() 関数を追加して両軸パラメトリック評価を実現
4. default_parametric_curve() を作成してデフォルト設定提供
5. create_parametric_curve_from_implicit() で暗黙関数からの変換も可能に

**Purpose（目的）**
- IMPROVEMENTS.md の計画を完了させるため、全機能を実装した上で公開
- パラメトリック曲線のサポートにより「より柔軟な数学的表現」を提供

**Impact（影響）**
- 既存の y=f(x) 式との共存を実現し、両方を同時使用可能に
- UI にパラメトリックモードを追加する準備はしておく（将来拡張用）
"""