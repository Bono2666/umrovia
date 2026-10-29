"""Pemeriksaan font PDF: setiap dokumen yang dibuat aplikasi hanya memuat Poppins."""
import re


def assert_poppins_only(content: bytes) -> None:
    fonts = set(re.findall(rb"/BaseFont\s*/([^\s/>]+)", content))
    assert fonts and all(b"Poppins" in name for name in fonts), fonts
