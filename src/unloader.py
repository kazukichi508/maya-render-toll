# ==============================================================================
# ファイル: unloader.py
# ==============================================================================
# 概要:
# Mayaのセッションから 'render_layer_tool' パッケージに関連する
# 全てのモジュールをアンロード（削除）するためのスクリプトです。
#
# このスクリプトを実行することで、Mayaを再起動することなく、
# ツールのコード変更を完全に反映させることができます。
#
# 使い方:
# 1. 'run.py', 'model.py', 'controller.py', 'view.py' などのファイルを
#    編集して保存します。
# 2. Mayaのスクリプトエディタで、まずこの 'unloader.py' を実行します。
#    "Successfully unloaded..." と表示されれば成功です。
# 3. 次に、'run.py' を実行してツールを再起動します。
#
# ==============================================================================

import sys

def unload_tool_modules():
    """
    'render_layer_tool'に関連するモジュールをsys.modulesから削除する。
    """
    # アンロードするモジュールのリスト
    # 依存関係の末端から順に（子が先、親が後）指定するのが安全です。
    modules_to_unload = [
        'render_layer_tool.run',
        'render_layer_tool.controller',
        'render_layer_tool.model',
        'render_layer_tool.view',
        'render_layer_tool' # パッケージ本体
    ]

    unloaded_count = 0
    print("--- Attempting to unload render_layer_tool modules ---")
    for module_name in modules_to_unload:
        if module_name in sys.modules:
            try:
                del sys.modules[module_name]
                print(f"Unloaded module: {module_name}")
                unloaded_count += 1
            except Exception as e:
                print(f"Could not unload {module_name}: {e}")
    
    if unloaded_count > 0:
        print(f"\nSuccessfully unloaded {unloaded_count} render_layer_tool module(s).")
        print("You can now re-run the tool to see your changes.")
    else:
        print("\nRender_layer_tool modules were not found in the current session.")

# --- スクリプトの実行 ---
if __name__ == "__main__":
    unload_tool_modules()