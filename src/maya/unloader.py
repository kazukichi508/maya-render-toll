# ==============================================================================
# ファイル: unloader.py
# ==============================================================================
# 概要:
# Mayaのセッションから 'render_layer_tool' パッケージに関連する
# 全てのモジュールをアンロード（削除）するためのスクリプトです。
#
# これにより、Mayaを再起動することなく、ツールのコード変更を
# 完全に反映させることができます。
#
# 使い方:
# 1. 'model.py', 'view.py', 'controller.py', 'run.py' などのファイルを
#    編集して保存します。
# 2. Mayaのスクリプトエディタで、まずこの 'unloader.py' を実行します。
#    "Successfully unloaded render_layer_tool modules." と表示されれば成功です。
# 3. 次に、'render_layer_tool.run.run()' を実行してツールを再起動します。
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
        'render_layer_tool.view',
        'render_layer_tool.model',
        'render_layer_tool' # パッケージ本体
    ]

    unloaded_count = 0
    for module_name in modules_to_unload:
        if module_name in sys.modules:
            try:
                del sys.modules[module_name]
                print(f"Unloaded module: {module_name}")
                unloaded_count += 1
            except Exception as e:
                print(f"Could not unload {module_name}: {e}")
    
    if unloaded_count > 0:
        print("\nSuccessfully unloaded render_layer_tool modules.")
        print("You can now re-run the tool to see your changes.")
    else:
        print("\nRender_layer_tool modules were not loaded in the first place.")


# --- スクリプトの実行 ---
if __name__ == "__main__":
    unload_tool_modules()

