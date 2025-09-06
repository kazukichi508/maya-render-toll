# -*- coding: utf-8 -*-
# render_layer_tool/view.py

from PySide6 import QtWidgets, QtCore, QtGui

class RenderLayerToolView(QtWidgets.QWidget):
    """
    UIを構築し、ウィジェット群を公開するView。
    """
    request_populate_tree = QtCore.Signal()
    request_add_to_target = QtCore.Signal(str) 
    request_remove_from_target = QtCore.Signal(str)
    request_create_layer = QtCore.Signal()
    request_layer_list_refresh = QtCore.Signal()
    request_delete_selected_layers = QtCore.Signal()
    request_delete_all_layers = QtCore.Signal()
    widget_closed = QtCore.Signal()
    search_text_changed = QtCore.Signal(str)
    request_apply_aov_preset = QtCore.Signal(str)

    def __init__(self, parent=None):
        super(RenderLayerToolView, self).__init__(parent)
        self.setWindowTitle("Render Layer Tool")
        self.setWindowFlags(QtCore.Qt.Window)
        self.resize(1150, 850)
        
        self._load_icons()
        self._build_ui()

    def _load_icons(self):
        """ノードタイプごとのアイコンをロードする。"""
        self.icons = {
            'camera': QtGui.QIcon(":/camera.svg"),
            'light': QtGui.QIcon(":/light.svg"),
            'geometry': QtGui.QIcon(":/mesh.svg"),
            'group': QtGui.QIcon(":/transform.svg"),
            'other': QtGui.QIcon(":/locator.svg"),
            'default': QtGui.QIcon(":/transform.svg")
        }

    def closeEvent(self, event):
        self.widget_closed.emit()
        super(RenderLayerToolView, self).closeEvent(event)

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        root.addWidget(main_splitter, 1)

        left_widget = self._create_scene_panel()
        main_splitter.addWidget(left_widget)

        right_widget = self._create_lists_panel()
        main_splitter.addWidget(right_widget)

        main_splitter.setSizes([500, 650])

        aov_box = self._create_aov_group()
        create_box = self._create_layer_creation_group()
        manage_box = self._create_layer_management_group()

        self.status_lbl = QtWidgets.QLabel("Ready.")
        self.status_lbl.setStyleSheet("color:#E0E0E0; padding:4px;")

        root.addWidget(aov_box)
        root.addWidget(create_box)
        root.addWidget(manage_box)
        root.addWidget(self.status_lbl)

        self._connect_signals()

    def _create_scene_panel(self):
        """シーン階層パネルの構築"""
        left_widget = QtWidgets.QWidget()
        left_v = QtWidgets.QVBoxLayout(left_widget)
        left_box = QtWidgets.QGroupBox("1) シーン選択 (階層表示/自動同期)")
        left_box_layout = QtWidgets.QVBoxLayout(left_box)

        search_layout = QtWidgets.QHBoxLayout()
        self.search_le = QtWidgets.QLineEdit()
        self.search_le.setPlaceholderText("オブジェクト名を検索...")
        self.clear_search_btn = QtWidgets.QToolButton()
        self.clear_search_btn.setText("X")
        search_layout.addWidget(QtWidgets.QLabel("検索:"))
        search_layout.addWidget(self.search_le)
        search_layout.addWidget(self.clear_search_btn)
        left_box_layout.addLayout(search_layout)

        self.scene_objects_tree = QtWidgets.QTreeWidget()
        self.scene_objects_tree.setHeaderLabels(["Name"])
        self.scene_objects_tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.scene_objects_tree.setAlternatingRowColors(True)

        selection_mode_box = QtWidgets.QGroupBox("リスト追加時の階層展開")
        selection_mode_layout = QtWidgets.QHBoxLayout(selection_mode_box)
        self.expand_groups_radio = QtWidgets.QRadioButton("子階層もすべて展開 (推奨)")
        self.groups_as_parents_radio = QtWidgets.QRadioButton("選択ノードのみ")
        self.expand_groups_radio.setChecked(True)
        self.expand_groups_radio.setToolTip("グループを選択した場合、その中にあるレンダリング可能なジオメトリをすべて個別に追加します。")
        self.groups_as_parents_radio.setToolTip("選択したノード（グループ含む）そのものを追加します。子階層は展開しません。")

        selection_mode_layout.addWidget(self.expand_groups_radio)
        selection_mode_layout.addWidget(self.groups_as_parents_radio)
        
        self.refresh_tree_btn = QtWidgets.QPushButton("手動で再構築")
        
        left_box_layout.addWidget(self.scene_objects_tree, 1)
        left_box_layout.addWidget(selection_mode_box)
        
        left_v.addWidget(left_box)
        left_v.addWidget(self.refresh_tree_btn)
        return left_widget

    def _create_lists_panel(self):
        right_widget = QtWidgets.QWidget()
        right_v = QtWidgets.QVBoxLayout(right_widget)
        
        list_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)

        target_box = QtWidgets.QGroupBox("2a) レンダリング対象 (主役)")
        target_v = QtWidgets.QVBoxLayout(target_box)
        self.target_list_widget = QtWidgets.QListWidget()
        self.target_list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.clear_target_btn = QtWidgets.QPushButton("リストをクリア")
        target_v.addWidget(self.target_list_widget, 1)
        
        target_h = QtWidgets.QHBoxLayout()
        self.add_target_btn = QtWidgets.QPushButton("▲ 対象へ追加/移動 ▲")
        self.remove_target_btn = QtWidgets.QPushButton("▼ 対象から戻す ▼")
        target_h.addWidget(self.add_target_btn)
        target_h.addWidget(self.remove_target_btn)
        target_h.addWidget(self.clear_target_btn)
        target_v.addLayout(target_h)
        list_splitter.addWidget(target_box)
        
        pvoff_box = QtWidgets.QGroupBox("2b) PV OFFリスト (影/反射用)")
        pvoff_v = QtWidgets.QVBoxLayout(pvoff_box)
        self.pvoff_list_widget = QtWidgets.QListWidget()
        self.pvoff_list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.clear_pvoff_btn = QtWidgets.QPushButton("リストをクリア")
        pvoff_v.addWidget(self.pvoff_list_widget, 1)

        pvoff_h = QtWidgets.QHBoxLayout()
        self.add_pvoff_btn = QtWidgets.QPushButton("▲ PV OFFへ追加/移動 ▲")
        self.remove_pvoff_btn = QtWidgets.QPushButton("▼ PV OFFから戻す ▼")
        pvoff_h.addWidget(self.add_pvoff_btn)
        pvoff_h.addWidget(self.remove_pvoff_btn)
        pvoff_h.addWidget(self.clear_pvoff_btn)
        pvoff_v.addLayout(pvoff_h)
        list_splitter.addWidget(pvoff_box)

        right_v.addWidget(list_splitter)
        return right_widget

    def _connect_signals(self):
        self.refresh_tree_btn.clicked.connect(self.request_populate_tree.emit)
        
        self.add_target_btn.clicked.connect(lambda: self.request_add_to_target.emit('target'))
        self.remove_target_btn.clicked.connect(lambda: self.request_remove_from_target.emit('target'))
        self.add_pvoff_btn.clicked.connect(lambda: self.request_add_to_target.emit('pvoff'))
        self.remove_pvoff_btn.clicked.connect(lambda: self.request_remove_from_target.emit('pvoff'))

        self.create_btn.clicked.connect(self.request_create_layer.emit)
        self.create_each_checkbox.stateChanged.connect(
            lambda state: self.layer_name_le.setEnabled(state == 0)
        )
        self.refresh_layers_btn.clicked.connect(self.request_layer_list_refresh.emit)
        self.delete_selected_btn.clicked.connect(self.request_delete_selected_layers.emit)
        self.delete_all_btn.clicked.connect(self.request_delete_all_layers.emit)
        
        self.scene_objects_tree.itemDoubleClicked.connect(lambda item, col: self._on_tree_double_clicked(item, 'target'))
        self.target_list_widget.itemDoubleClicked.connect(lambda item: self.request_remove_from_target.emit('target'))
        self.pvoff_list_widget.itemDoubleClicked.connect(lambda item: self.request_remove_from_target.emit('pvoff'))

        self.search_le.textChanged.connect(self.search_text_changed.emit)
        self.clear_search_btn.clicked.connect(lambda: self.search_le.clear())
        
        self.clear_target_btn.clicked.connect(self.target_list_widget.clear)
        self.clear_pvoff_btn.clicked.connect(self.pvoff_list_widget.clear)

    def _on_tree_double_clicked(self, item, target_list_name):
        if item.data(0, QtCore.Qt.UserRole):
            self.scene_objects_tree.clearSelection()
            item.setSelected(True)
            self.request_add_to_target.emit(target_list_name)

    def populate_scene_tree_hierarchy(self, categorized_data):
        self.scene_objects_tree.blockSignals(True)
        self.scene_objects_tree.clear()

        category_map = {
            "groups": "グループ",
            "objects": "オブジェクト",
            "other": "その他"
        }
        category_order = ["groups", "objects", "other"]

        category_items = {}
        for key in category_order:
            if categorized_data.get(key):
                display_name = category_map.get(key)
                header = QtWidgets.QTreeWidgetItem(self.scene_objects_tree)
                header.setText(0, display_name)
                font = header.font(0)
                font.setBold(True)
                header.setFont(0, font)
                header.setFlags(header.flags() & ~QtCore.Qt.ItemIsSelectable)
                category_items[key] = header

        def create_item_recursive(parent_widget, node_path, node_data):
            short_name = node_path.split('|')[-1]
            item = QtWidgets.QTreeWidgetItem(parent_widget)
            item.setText(0, short_name)
            item.setData(0, QtCore.Qt.UserRole, node_path)
            
            node_type = node_data.get('type', 'default')
            icon = self.icons.get(node_type, self.icons['default'])
            if icon and not icon.isNull():
                item.setIcon(0, icon)

            children_data = node_data.get('children', {})
            sorted_children = sorted(children_data.items(), key=lambda x: x[0].split('|')[-1].lower())
            
            for child_path, child_data in sorted_children:
                create_item_recursive(item, child_path, child_data)

        for category_key in category_order:
            parent_item = category_items.get(category_key)
            if parent_item:
                root_nodes = categorized_data.get(category_key, {})
                sorted_nodes = sorted(root_nodes.items(), key=lambda x: x[0].split('|')[-1].lower())
                for node_path, node_data in sorted_nodes:
                    create_item_recursive(parent_item, node_path, node_data)

        self.scene_objects_tree.expandAll()
        self.scene_objects_tree.blockSignals(False)

    def filter_scene_tree(self, text):
        text = text.strip().lower()
        root = self.scene_objects_tree.invisibleRootItem()
        for i in range(root.childCount()):
            category_item = root.child(i)
            has_visible_child = False
            for j in range(category_item.childCount()):
                child_item = category_item.child(j)
                is_match = text in child_item.text(0).lower()
                child_item.setHidden(not is_match)
                if is_match:
                    has_visible_child = True
            category_item.setHidden(not has_visible_child)
            if has_visible_child:
                category_item.setExpanded(True)
            else:
                category_item.setExpanded(False)

    def sync_tree_selection(self, paths_to_select):
        self.scene_objects_tree.clearSelection()
        if not paths_to_select: return

        selection_set = set(paths_to_select)
        first_selected_item = None

        iterator = QtWidgets.QTreeWidgetItemIterator(self.scene_objects_tree, QtWidgets.QTreeWidgetItemIterator.Selectable)
        while iterator.value():
            item = iterator.value()
            item_path = item.data(0, QtCore.Qt.UserRole)
            if item_path in selection_set:
                item.setSelected(True)
                if not first_selected_item: first_selected_item = item
                
                parent = item.parent()
                while parent:
                    parent.setExpanded(True)
                    parent = parent.parent()
            iterator += 1

        if first_selected_item:
             self.scene_objects_tree.scrollToItem(first_selected_item, QtWidgets.QAbstractItemView.PositionAtCenter)

    def _create_aov_group(self):
        aov_box = QtWidgets.QGroupBox("AOV 設定（Arnold）")
        main_layout = QtWidgets.QVBoxLayout(aov_box)
        preset_layout = QtWidgets.QHBoxLayout()
        preset_layout.addWidget(QtWidgets.QLabel("<b>Presets:</b>"))
        preset_buttons = ["Basic", "Full Beauty", "Utility", "Clear"]
        for name in preset_buttons:
            btn = QtWidgets.QPushButton(name)
            btn.clicked.connect(lambda checked=False, name=name: self.request_apply_aov_preset.emit(name))
            preset_layout.addWidget(btn)
        preset_layout.addStretch()
        main_layout.addLayout(preset_layout)

        self.aov_checkboxes = {}
        
        def add_checkboxes(layout, label, names):
            layout.addWidget(QtWidgets.QLabel(f"<b>{label}:</b>"))
            for name in names:
                cb = QtWidgets.QCheckBox(name)
                self.aov_checkboxes[name] = cb
                layout.addWidget(cb)
            layout.addStretch()

        beauty_l = QtWidgets.QHBoxLayout()
        beauty_aovs = ["diffuse", "specular", "coat", "transmission", "sss", "volume", "emission", "background"]
        add_checkboxes(beauty_l, "Beauty", beauty_aovs)
        
        util_l = QtWidgets.QHBoxLayout()
        util_aovs = ["id", "shadow_matte", "N", "P", "AO"]
        add_checkboxes(util_l, "Utility", util_aovs)
        
        main_layout.addLayout(beauty_l)
        main_layout.addLayout(util_l)
        return aov_box

    def get_aov_settings(self):
        return {name: cb.isChecked() for name, cb in self.aov_checkboxes.items()}

    def set_aov_checkboxes(self, target_aovs):
        for name, cb in self.aov_checkboxes.items():
            cb.setChecked(name in target_aovs)

    def _create_layer_creation_group(self):
        create_box = QtWidgets.QGroupBox("3) レイヤー作成")
        main_layout = QtWidgets.QVBoxLayout(create_box)
        settings_l = QtWidgets.QHBoxLayout()
        self.layer_name_le = QtWidgets.QLineEdit()
        self.layer_name_le.setPlaceholderText("例: RL_Character_Solo")
        
        self.auto_matte_checkbox = QtWidgets.QCheckBox("自動マット化 (Soloモード)")
        self.auto_matte_checkbox.setChecked(True)
        self.auto_matte_checkbox.setToolTip(
            "ON: 「対象リスト」と「PV OFFリスト」以外の全オブジェクトを自動的にマット化(PV Off)します。\n"
            "OFF: リスト以外のオブジェクトはそのまま表示されます。"
        )

        self.create_each_checkbox = QtWidgets.QCheckBox("個別作成")
        self.create_each_checkbox.setToolTip("「対象リスト」内の各オブジェクトに対して個別にレイヤーを作成します。（PV OFFリストは共通）")
        
        settings_l.addWidget(QtWidgets.QLabel("レイヤー名:"))
        settings_l.addWidget(self.layer_name_le, 1)
        settings_l.addWidget(self.auto_matte_checkbox)
        settings_l.addWidget(self.create_each_checkbox)
        
        self.create_btn = QtWidgets.QPushButton("レンダーレイヤー作成")
        self.create_btn.setStyleSheet("font-weight: bold; padding: 5px;")

        main_layout.addLayout(settings_l)
        main_layout.addWidget(self.create_btn)
        return create_box

    def _create_layer_management_group(self):
        manage_box = QtWidgets.QGroupBox("既存レンダーレイヤーの管理 (自動更新)")
        layout = QtWidgets.QHBoxLayout(manage_box)
        self.layer_list_widget = QtWidgets.QListWidget()
        self.layer_list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        button_layout = QtWidgets.QVBoxLayout()
        self.refresh_layers_btn = QtWidgets.QPushButton("手動更新")
        self.delete_selected_btn = QtWidgets.QPushButton("選択を削除")
        self.delete_all_btn = QtWidgets.QPushButton("全て削除")
        self.delete_all_btn.setStyleSheet("background-color: #A04040;")
        button_layout.addWidget(self.refresh_layers_btn)
        button_layout.addWidget(self.delete_selected_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.delete_all_btn)
        layout.addWidget(self.layer_list_widget, 1)
        layout.addLayout(button_layout)
        return manage_box

    def set_status(self, text, color="#7EE081"):
        self.status_lbl.setText(f"<span style='color:{color}'>{text}</span>")
        
    def populate_render_layer_list(self, layer_names):
        self.layer_list_widget.clear()
        self.layer_list_widget.addItems(layer_names)