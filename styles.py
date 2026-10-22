READER_QSS = """
#CentralWidget {
    background-color: rgba(15, 20, 25, 0.88);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
}

QScrollBar:vertical {
    border: none;
    background: transparent;
    width: 8px;
    margin: 12px 2px 12px 0;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.15);
    min-height: 24px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: rgba(255, 255, 255, 0.25);
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
    background: none;
}

#Header {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(20, 26, 32, 0.95),
        stop:1 rgba(30, 38, 45, 0.95));
    border-top-left-radius: 16px;
    border-top-right-radius: 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    min-height: 50px;
}

#ReaderArea {
    background-color: transparent;
    border: none;
    padding: 26px 30px 30px 30px;
    font-family: 'Segoe UI', 'Microsoft YaHei UI', sans-serif;
    selection-background-color: rgba(94, 151, 246, 0.35);
    selection-color: #ffffff;
}

QPushButton {
    background-color: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.08);
    color: rgba(255, 255, 255, 0.85);
    padding: 7px 14px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: rgba(255, 255, 255, 0.12);
    border: 1px solid rgba(255, 255, 255, 0.15);
    color: #ffffff;
}

QPushButton:pressed {
    background-color: rgba(0, 0, 0, 0.3);
}

QPushButton::menu-indicator {
    image: none;
}

#TOCButton {
    text-align: left;
    min-width: 82px;
}
QMenu { background: #1D2C2A; color: #E2ECE6; border: 1px solid #3C554D; padding: 6px; }
QMenu::item { padding: 8px 18px; }
QMenu::item:selected { background: #315B4B; border-radius: 4px; }
QSizeGrip { background: transparent; width: 14px; height: 14px; }
"""


LIBRARY_QSS = """
QWidget {
    background-color: #F4F5F1;
    color: #243A36;
    font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
    font-size: 13px;
}
QLabel { background: transparent; color: #627670; }
#BrandTitle { color: #193F37; font-size: 28px; font-weight: 700; }
#PageTitle { color: #193F37; font-size: 23px; font-weight: 700; }
#Subtitle { color: #6D807A; font-size: 14px; }
#Badge { color: #398176; background: #E5EFEB; border-radius: 8px; padding: 6px 10px; font-size: 11px; }
#SelectedTitle { color: #254A40; font-size: 17px; font-weight: 600; }
#EmptyState { color: #7B8E85; padding: 28px; font-size: 15px; }
#Muted { color: #83918B; font-size: 12px; }
#Sidebar, #SidebarScroll { background: transparent; border: none; }
QGroupBox {
    background: #FFFFFF; border: 1px solid #E0E6DD; border-radius: 14px;
    margin-top: 12px; padding: 18px 14px 14px; font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 16px; padding: 0 6px; color: #477366; }
QLineEdit, QComboBox, QPlainTextEdit {
    background: #F7F9F6; color: #29483F; border: 1px solid #DCE4DA;
    border-radius: 8px; padding: 9px 10px; selection-background-color: #C7E5DA;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { border: 1px solid #349B86; }
QLineEdit:disabled, QComboBox:disabled { color: #9AA69E; background: #EEF0EC; }
QListWidget { background: #FFFFFF; border: none; outline: none; padding: 4px 0; }
QListWidget::item { padding: 16px 12px; border: 1px solid #E9EDE6; border-radius: 9px; color: #3E554B; }
QListWidget::item:selected { background: #E2F1E9; border: 1px solid #9CCDB9; color: #176553; }
QListWidget::item:hover:!selected { background: #F4F8F1; border-color: #D8E5D8; }
QComboBox { min-height: 18px; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: #FFFFFF; color: #254A40; selection-background-color: #DAEEE3; border: 1px solid #C9D9CB; }
QPushButton {
    background: #F0F5EF; border: 1px solid #D8E3D6; color: #39604F;
    border-radius: 8px; padding: 10px 14px; font-weight: 500;
}
QPushButton:hover { background: #E2EEE2; border-color: #A6C7B2; }
QPushButton:pressed { background: #D5E6D8; }
QPushButton:disabled { color: #A0ADA3; background: #F1F3EF; border-color: #E7EBE4; }
QPushButton#PrimaryButton { background: #147D73; border-color: #147D73; color: #FFFFFF; font-weight: 600; }
QPushButton#PrimaryButton:hover { background: #106B63; }
QPushButton#PrimaryButton:pressed { background: #0D574F; }
QPushButton#PrimaryButton:disabled { background: #C4D6CD; border-color: #C4D6CD; color: #F9FCF9; }
QPushButton#DangerButton { color: #A67366; background: #FFFFFF; }
QPushButton#DangerButton:hover { background: #FFF1ED; border-color: #E4BDB2; }
QPushButton#DangerButton:disabled { color: #BCC2BA; border-color: #E7EBE4; }
QPushButton#QuietButton { border: none; background: transparent; color: #6E8A7D; padding: 4px 6px; font-size: 12px; }
QPushButton#QuietButton:hover { color: #147D73; }
QSlider::groove:horizontal { height: 5px; background: #E3EAE0; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #64AB91; border-radius: 2px; }
QSlider::handle:horizontal { background: #147D73; border: 3px solid #FFFFFF; width: 14px; height: 14px; margin: -7px 0; border-radius: 10px; }
QCheckBox { spacing: 9px; background: transparent; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #B9CDBE; background: #F7FAF5; border-radius: 5px; }
QCheckBox::indicator:checked { background: #147D73; border: 4px solid #AFD8C7; }
QProgressBar { background: #E7EEE3; border: none; border-radius: 6px; color: #254A40; min-height: 18px; text-align: center; }
QProgressBar::chunk { background: #79B6A0; border-radius: 6px; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: #CFDCCF; min-height: 28px; border-radius: 3px; }
QScrollBar::handle:vertical:hover { background: #A5C5B1; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip { background: #244F42; color: #FFFFFF; border: none; padding: 6px; }
"""

QSS = READER_QSS
