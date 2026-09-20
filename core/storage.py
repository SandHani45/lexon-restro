# core/storage.py
import os

import cloudinary.uploader
from cloudinary_storage.storage import MediaCloudinaryStorage as _BaseMediaCloudinaryStorage


class RestaurantMediaCloudinaryStorage(_BaseMediaCloudinaryStorage):
    """
    Cloudinary's own `unique_filename` option defaults to True, so every
    upload gets a random suffix appended to its public_id on top of
    whatever name we already computed via upload_to (menu_item_image_path /
    tenant_logo_path). That's redundant -- Django's own Storage.save()
    already calls get_available_name() (which checks exists()) before
    _upload() ever runs, so the name reaching here is already guaranteed
    free -- and it's actively harmful: a long AI-generated filename (menu
    photos are routinely named things like
    "Gemini_Generated_Image_xxxxx.webp") plus Cloudinary's own suffix can
    push the stored path past ImageField's default max_length=100,
    producing a DataError at save time that has nothing to do with the
    image itself (this broke the very first real upload after switching to
    Cloudinary). Disabling it keeps the exact deterministic
    restaurants/<slug>/menu_items/<name> path our own upload_to functions
    computed.
    """

    def _upload(self, name, content):
        options = {
            "use_filename": True,
            "unique_filename": False,
            "resource_type": self._get_resource_type(name),
            "tags": self.TAG,
        }
        folder = os.path.dirname(name)
        if folder:
            options["folder"] = folder
        return cloudinary.uploader.upload(content, **options)
