# render_layer_tool/model.py
# -*- coding: utf-8 -*-
import maya.cmds as cmds
import logging
import traceback
import re

# Render Setup APIのインポート
try:
    import maya.app.renderSetup.model.renderSetup as rs
    import maya.app.renderSetup.model.override as override
    import maya.app.renderSetup.model.selector as selector
    # 【安定性向上】評価遅延(deferredEvaluation)のために内部モジュールをインポート
    try:
        import maya.app.renderSetup.model.renderSetupInternal as rsInternal
    except ImportError:
        rsInternal = None
        logging.info("maya.app.renderSetup.model.renderSetupInternal not found. Deferred Evaluation will be disabled.")

except ImportError:
    rs = None
    logging.error("Maya Render Setup API not found. Tool cannot function.")

class RenderLayerManager:
    """
    レンダーレイヤー、コレクション、オーバーライドの作成と管理。
    """
    def __init__(self):
        if rs is None:
            raise EnvironmentError("Render Setup API is not available.")
        self.rs_instance = rs.instance()
        
        # AOVプリセット定義 (変更なし)
        self.AOV_PRESETS = {
            "Basic": ["diffuse", "specular", "N", "P"],
            "Full Beauty": ["diffuse", "specular", "coat", "transmission", "sss", "volume", "emission", "background"],
            "Utility": ["id", "shadow_matte", "N", "P", "AO"],
            "Clear": []
        }

    def get_aov_preset(self, preset_name):
        return self.AOV_PRESETS.get(preset_name, [])

    def list_render_layers(self):
        """デフォルトレイヤー(masterLayer)以外の全てのレンダーレイヤー名をリストアップします。"""
        try:
            layers = self.rs_instance.getRenderLayers()
            # layerオブジェクト自体が無効な場合も考慮してチェック
            return sorted([layer.name() for layer in layers if layer and not layer.isDefault()])
        except Exception as e:
            logging.error(f"レンダーレイヤーのリストアップ中にエラー: {e}")
            return []

    def _sanitize_name(self, name):
        """Mayaノード名として有効な名前にサニタイズし、RL_プレフィックスを付与します。"""
        # オブジェクト名からネームスペースやパイプを除去
        cleaned_name = name.split('|')[-1].split(':')[-1]
        
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', cleaned_name)
        
        if not sanitized:
            sanitized = "Unnamed"
        elif sanitized and sanitized[0].isdigit():
             sanitized = "Object_" + sanitized

        if not sanitized.startswith("RL_"):
            sanitized = "RL_" + sanitized
            
        return sanitized

    def create_render_layers(self, base_name, target_list, pvoff_list, settings):
        """
        指定された設定に基づいてレンダーレイヤーを作成します。(Undo管理はControllerで行う)
        """
        create_each = settings.get('create_each', False)
        layers_to_create = []
        
        # 1. 作成するレイヤーのリストとベース名を決定する (変更なし)
        if create_each:
            if not target_list:
                raise ValueError("個別作成モードでは、対象リストに最低1つのオブジェクトが必要です。")
            for obj in target_list:
                layer_name = self._sanitize_name(obj)
                layers_to_create.append((layer_name, [obj]))
        else:
            final_base_name = base_name.strip() if base_name else ""
            if not final_base_name:
                if target_list:
                    final_base_name = target_list[0]
                elif pvoff_list:
                     final_base_name = "Scene_PVOff"
                else:
                    final_base_name = "Scene"
            
            layer_name = self._sanitize_name(final_base_name)
            layers_to_create.append((layer_name, target_list))

        # 2. 既存レイヤー名の取得（重複チェック用）
        existing_layer_names = set()
        try:
            all_layers = self.rs_instance.getRenderLayers()
            existing_layer_names = {layer.name() for layer in all_layers if layer}
        except Exception as e:
            logging.error(f"既存レイヤー名の取得に失敗しました。: {e}")

        created_count = 0
        
        # 3. 作成実行
        # 【安定性向上】評価遅延コンテキストを開始
        # これにより、内部でのRender Setupの更新がバッチ処理され、安定性が向上する
        try:
            if rsInternal:
                logging.debug("Starting layer creation with Deferred Evaluation.")
                with rsInternal.deferredEvaluation(True):
                    created_count = self._execute_layer_creation(layers_to_create, existing_layer_names, pvoff_list, settings)
            else:
                # 利用できない場合は通常通り実行
                logging.debug("Starting layer creation without Deferred Evaluation.")
                created_count = self._execute_layer_creation(layers_to_create, existing_layer_names, pvoff_list, settings)
        except Exception as e:
            logging.error(f"レイヤー作成バッチ処理中にエラーが発生しました: {e}")
            # 評価遅延中にエラーが発生した場合、Controller側でUndoされるため、例外を再送出する
            raise
            
        return created_count

    def _execute_layer_creation(self, layers_to_create, existing_layer_names, pvoff_list, settings):
        """レイヤー作成の実行部分（評価遅延コンテキスト内で実行される）"""
        created_count = 0
        for layer_name_base, targets in layers_to_create:
            
            # ユニークな名前の決定
            final_layer_name = layer_name_base
            counter = 1
            
            # 既存レイヤー名、またはシーン内の他のノード名(cmds.objExists)と衝突しなくなるまでループ
            while final_layer_name in existing_layer_names or cmds.objExists(final_layer_name):
                 final_layer_name = f"{layer_name_base}_{counter}"
                 counter += 1

            # ユニークな名前でレイヤー構造を作成
            if self._create_single_layer_structure(final_layer_name, targets, pvoff_list, settings):
                created_count += 1
                # バッチ内での重複を防ぐ
                existing_layer_names.add(final_layer_name)
        return created_count


    def _create_single_layer_structure(self, layer_name, target_objects, pvoff_objects, settings):
        """
        単一のレンダーレイヤーとコレクション構造を作成します。
        失敗時は自動的にクリーンアップ（ロールバック）を行います。
        """
        auto_matte = settings.get('auto_matte', True)
        aov_settings = settings.get('aov_settings', {})
        final_name = layer_name

        layer = None
        try:
            # 1. レイヤー作成
            layer = self.rs_instance.createRenderLayer(final_name)
            if not layer:
                 raise RuntimeError(f"Render Layer object creation returned None for {final_name}")

            # 存在するオブジェクトのみをフィルタリング
            valid_targets = [obj for obj in target_objects if cmds.objExists(obj)]
            valid_pvoffs = [obj for obj in pvoff_objects if cmds.objExists(obj)]
            all_valid_objects = list(set(valid_targets) | set(valid_pvoffs))

            # 2. コレクション作成（作成順 = 優先度 低 -> 高）

            # 2a. Auto Matte (Soloモード) 用ベースコレクション
            if auto_matte:
                # 優先度 低: ワールドマット
                world_matte_col = layer.createCollection(f"COL_{final_name}_WorldMatte")
                world_matte_col.getSelector().setPattern('*')
                self._apply_primary_visibility_override(world_matte_col, enabled=False)

                # 優先度 中: 表示維持
                if all_valid_objects:
                    visible_col = layer.createCollection(f"COL_{final_name}_Visible")
                    visible_col.getSelector().staticSelection.set(all_valid_objects)
                    self._apply_primary_visibility_override(visible_col, enabled=True)

            # 2b. Target Collection (主役)
            if valid_targets:
                target_col = layer.createCollection(f"COL_{final_name}_Target")
                target_col.getSelector().staticSelection.set(valid_targets)

            # 2c. PV OFF Collection (影/反射用)
            if valid_pvoffs:
                pvoff_col = layer.createCollection(f"COL_{final_name}_PVOff")
                pvoff_col.getSelector().staticSelection.set(valid_pvoffs)
                self._apply_primary_visibility_override(pvoff_col, enabled=False)

            # 3. AOV設定 (Arnold前提)
            self._setup_aov_overrides(layer, aov_settings)

            return True

        except Exception as e:
            # 【安定化】エラーハンドリングとクリーンアップ（ロールバック）
            logging.error(f"レンダーレイヤー構造の作成中にエラーが発生しました ({final_name}): {e}")
            traceback.print_exc()
            
            # 失敗時はクリーンアップ
            # 作成途中のレイヤーが残るとシーンが不安定になるため、確実に削除を試みる
            if layer:
                try:
                    self._cleanup_failed_layer(layer)
                    logging.info(f"Cleanup: Removed partially created layer {final_name}.")
                except Exception as cleanup_e:
                    # クリーンアップ自体の失敗は致命的
                    logging.error(f"致命的エラー: 失敗したレイヤーのクリーンアップにも失敗しました: {cleanup_e}")
            return False

    def _apply_primary_visibility_override(self, parent_collection, enabled=True):
        """
        Primary Visibilityのオーバーライドを適用します。(安定化対策適用)
        """
        shapes_col_name = f"{parent_collection.name()}_Shapes"
        
        try:
            shapes_col = parent_collection.createCollection(shapes_col_name)
        except Exception as e:
            logging.error(f"サブコレクションの作成に失敗しました: {e}")
            return
        
        shapes_col.getSelector().setPattern('*')

        # kShapes フィルター
        # 【安定化】APIが利用可能か確認してから適用する
        try:
            if hasattr(selector.Filters, 'kShapes'):
                shapes_col.getSelector().setFilterType(selector.Filters.kShapes)
            else:
                 logging.info("selector.Filters.kShapes not found. Applying PV override without specific shape filter.")
        except Exception as e:
             # setFilterType自体が失敗する場合も考慮
             logging.warning(f"Failed to set filter type kShapes: {e}")

        # 絶対オーバーライドを作成
        ov_name = f"OVR_PV_{'On' if enabled else 'Off'}"
        pv_override = None
        
        # 【安定化】方法1: 推奨される新しいAPI (createAbsoluteOverride)
        try:
            pv_override = shapes_col.createAbsoluteOverride('shape', 'primaryVisibility')
            pv_override.setAttrValue(enabled)
        except Exception as e:
             logging.warning(f"PV override Method 1 failed. Trying fallback Method 2. Error: {e}")

        # 【安定化】方法2: フォールバック (古いAPI)
        if pv_override is None:
             try:
                 pv_override = shapes_col.createOverride(ov_name, override.AbsOverride.kTypeId)
                 pv_override.setAttributeName("primaryVisibility")
                 pv_override.setAttrValue(enabled)
             except Exception as e2:
                 logging.error(f"Failed to apply Primary Visibility override to {parent_collection.name()} using any method: {e2}")

    def _setup_aov_overrides(self, layer, aov_settings):
        """AOV設定のオーバーライドを適用します。(Arnold専用)"""
        if not cmds.pluginInfo('mtoa', query=True, loaded=True):
            return
        try:
            current_aov_nodes = cmds.ls(type='aiAOV')
            aov_map = {}
            for node in current_aov_nodes:
                try:
                    aov_name = cmds.getAttr(f"{node}.name")
                    aov_map[aov_name] = node
                except:
                    continue # アトリビュートが読めない場合はスキップ

            if not aov_map: return

            col_aov_root = layer.createCollection(f"COL_{layer.name()}_AOV_Settings")

            for aov_name, enabled in aov_settings.items():
                if aov_name in aov_map:
                    aov_node = aov_map[aov_name]
                    try:
                        col_single_aov = col_aov_root.createCollection(f"COL_AOV_{aov_name}")
                        col_single_aov.getSelector().setPattern(aov_node)
                        enabled_override = col_single_aov.createAbsoluteOverride('aiAOV', 'enabled')
                        enabled_override.setAttrValue(enabled)
                    except Exception as e:
                        logging.warning(f"AOV '{aov_name}' のオーバーライド設定に失敗しました: {e}")
        except Exception as e:
             logging.error(f"AOVオーバーライドの適用中にエラーが発生しました: {e}")

    def _cleanup_failed_layer(self, layer):
        """作成に失敗したレイヤーを安全に削除するヘルパーメソッド。"""
        if not layer: return
        
        # 念のためマスターレイヤーに切り替える（評価遅延中でも有効）
        try:
            if self.rs_instance.getVisibleRenderLayer() == layer:
                master_layer = self.rs_instance.getDefaultRenderLayer()
                self.rs_instance.switchToLayer(master_layer)
        except Exception:
            pass
        
        rs.delete(layer)

    def delete_render_layer(self, layer_name):
        """指定された名前のレンダーレイヤーを削除します。"""
        try:
            layer = None
            # 安全にレイヤーリストを取得
            try:
                all_layers = self.rs_instance.getRenderLayers()
            except Exception:
                return False

            # 名前で検索
            for lyr in all_layers:
                try:
                    if lyr and lyr.name() == layer_name:
                        layer = lyr
                        break
                except Exception:
                     continue
            
            if layer and not layer.isDefault():
                # 現在のレイヤーが削除対象の場合、マスターレイヤーに切り替える
                try:
                    if self.rs_instance.getVisibleRenderLayer() == layer:
                        master_layer = self.rs_instance.getDefaultRenderLayer()
                        self.rs_instance.switchToLayer(master_layer)
                except Exception as switch_e:
                    # 切り替え失敗は致命的ではないが警告
                    logging.warning(f"マスターレイヤーへの切り替えに失敗: {switch_e}")
                
                # レイヤーを削除
                rs.delete(layer)
                return True
            return False
        except Exception as e:
            logging.warning(f"レイヤー '{layer_name}' の削除中に予期せぬエラーが発生: {e}")
            return False

    def delete_multiple_layers(self, layer_names):
        """指定された複数のレイヤーを削除します。(安定性向上)"""
        count = 0
        
        # 【安定性向上】評価遅延コンテキストを開始
        try:
            if rsInternal:
                logging.debug("Starting batch delete with Deferred Evaluation.")
                with rsInternal.deferredEvaluation(True):
                   for name in layer_names:
                        if self.delete_render_layer(name):
                            count += 1
            else:
                 # 利用できない場合は通常通り実行
                 logging.debug("Starting batch delete without Deferred Evaluation.")
                 for name in layer_names:
                    if self.delete_render_layer(name):
                        count += 1
        except Exception as e:
            logging.error(f"レイヤー削除バッチ処理中にエラーが発生しました: {e}")
            # エラーが発生した場合でも、それまでに削除できた数を返す
            
        return count