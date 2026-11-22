from functools import cached_property

from app.modules.affine.service import fit_sheets
from app.modules.coordinates.service import convert
from app.modules.intake.service import acquire_bundle, intake
from app.modules.pairing.service import pair_controls
from app.modules.refit.service import refit_sheets
from app.modules.seams.service import check_seams


class Survey:
    def __init__(self, settings, options):
        self.options = options
        self.bundle = acquire_bundle(settings.sample_root, options.dataset)

    @cached_property
    def intake(self):
        return intake(self.bundle)

    @property
    def catalog(self):
        return self.intake['catalog']

    @cached_property
    def coordinates(self):
        return convert(self.intake)

    @cached_property
    def pairing(self):
        return pair_controls(self.coordinates, self.catalog)

    @cached_property
    def affine(self):
        return fit_sheets(self.pairing, self.catalog)

    @cached_property
    def refit(self):
        return refit_sheets(self.pairing, self.affine, self.catalog, self.options.control_limit_m)

    @cached_property
    def seams(self):
        return check_seams(self.intake, self.coordinates, self.pairing, self.refit, self.options.seam_limit_m)
