"""Exception domain trial — kode error mengikuti Spec §8.9 (huruf besar)."""
from rest_framework import status

from common.api import ProblemDetailAPIException


class TrialQuotaExceeded(ProblemDetailAPIException):
    """Kuota booking dummy trial habis (POL-08 / TR02)."""

    status_code = status.HTTP_403_FORBIDDEN
    default_code = "TRIAL_QUOTA_EXCEEDED"
    default_title = "Trial quota exceeded"
    default_detail = "Kuota booking demo trial sudah habis."


class TrialUserLimit(ProblemDetailAPIException):
    """Jumlah internal user trial mencapai batas (POL-08 / TR04)."""

    status_code = status.HTTP_403_FORBIDDEN
    default_code = "TRIAL_USER_LIMIT"
    default_title = "Trial user limit"
    default_detail = "Jumlah internal user trial mencapai batas."


class TrialAlreadyUsed(ProblemDetailAPIException):
    """Trial sudah terkonversi/berakhir — operasi demo ditutup (TR09)."""

    status_code = status.HTTP_403_FORBIDDEN
    default_code = "TRIAL_ALREADY_USED"
    default_title = "Trial already used"
    default_detail = "Trial sudah berakhir atau terkonversi; operasi demo ditutup."
