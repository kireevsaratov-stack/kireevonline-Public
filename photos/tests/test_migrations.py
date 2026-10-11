"""Шаги изменения базы (миграции) — по-настоящему: тестовая база откатывается и накатывается."""

import os
import tempfile

from django.test import TransactionTestCase, override_settings


class MigrationTestCase(TransactionTestCase):
    """Основа: база откатывается до шага `before`, в ней создаются данные «как было тогда»
    (разделы и альбомы назывались Category/SubCategory), после теста база возвращается к последнему шагу."""

    before = step = None

    def migrate(self, target):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        targets = [target] if isinstance(target, tuple) else target
        MigrationExecutor(connection).migrate(targets)
        return MigrationExecutor(connection).loader.project_state(targets).apps

    def setUp(self):
        from django.db import connection
        from django.db.migrations.loader import MigrationLoader

        self.latest = MigrationLoader(connection).graph.leaf_nodes()
        self.tmp = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.tmp.name)
        self.override.enable()
        old = self.migrate(self.before)
        Category, SubCategory, Photo = (old.get_model('photos', m) for m in ('Category', 'SubCategory', 'Photo'))
        cat = Category.objects.create(name='Репортаж', slug='reportazh')
        for pk, name in ((5, 'Фотовидеофест 2025'), (12, 'Прогулки 2024'), (19, 'Фотовыезд 2023')):
            SubCategory.objects.create(pk=pk, category=cat, name=name)
        for pk, title, album in (
            (3614, 'DSC02339', 5),
            (3615, 'IMG_1277', 5),
            (3616, '6Q0A9921', 12),
            (3619, '6Q0A9974', 12),
        ):
            Photo.objects.create(
                pk=pk,
                title=title,
                category=cat,
                subcategory_id=album,
                image=f'photos/2026/06/{title}.jpg',
                thumb=f'thumbs/2026/06/{title}_t.jpg',
            )

    def tearDown(self):
        self.migrate(self.latest)
        self.override.disable()
        self.tmp.cleanup()


class DamagedPhotosMigrationTests(MigrationTestCase):
    """0009: 4 повреждённых фото меняются при выкладке, откат возвращает всё как было."""

    before, step = ('photos', '0008_album_details'), ('photos', '0009_fix_damaged_photos')

    def test_forward_replaces_moves_and_trashes_then_backward_restores(self):
        P = self.migrate(self.step).get_model('photos', 'Photo')
        self.assertEqual(P.objects.get(pk=3615).subcategory_id, 19)
        for pk in (3615, 3616, 3619):
            p = P.objects.get(pk=pk)
            self.assertTrue(p.image.name.startswith('photos/replaced-2026-10/'))
            self.assertTrue(os.path.exists(os.path.join(self.tmp.name, p.image.name)))
            self.assertTrue(os.path.exists(os.path.join(self.tmp.name, p.thumb.name)))
        self.assertTrue(P.objects.get(pk=3614).is_deleted)

        P = self.migrate(self.before).get_model('photos', 'Photo')
        self.assertEqual(P.objects.get(pk=3615).subcategory_id, 5)
        self.assertEqual(P.objects.get(pk=3616).image.name, 'photos/2026/06/6Q0A9921.jpg')
        self.assertFalse(P.objects.get(pk=3614).is_deleted)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, 'photos', 'replaced-2026-10', 'IMG_1277.jpg')))

    def test_photo_fixed_by_hand_is_left_alone(self):
        old = self.migrate(self.before)
        old.get_model('photos', 'Photo').objects.filter(pk=3616).update(image='photos/2026/10/6Q0A9921.jpg')
        P = self.migrate(self.step).get_model('photos', 'Photo')
        self.assertEqual(P.objects.get(pk=3616).image.name, 'photos/2026/10/6Q0A9921.jpg')


class RenameSectionAlbumMigrationTests(MigrationTestCase):
    """0014: «категория/подкатегория» → «раздел/альбом» — данные целы в обе стороны."""

    before, step = ('photos', '0013_travel_lines'), ('photos', '0014_rename_section_album')

    def test_rename_keeps_data_both_ways(self):
        new = self.migrate(self.step)
        P, A, S = (new.get_model('photos', m) for m in ('Photo', 'Album', 'Section'))
        self.assertEqual(P.objects.get(pk=3615).album.name, 'Фотовидеофест 2025')
        self.assertEqual(A.objects.get(pk=19).section.name, 'Репортаж')
        self.assertEqual(S.objects.get().albums.count(), 3)
        old = self.migrate(self.before)
        self.assertEqual(old.get_model('photos', 'Photo').objects.get(pk=3615).subcategory.name, 'Фотовидеофест 2025')
        self.assertEqual(old.get_model('photos', 'SubCategory').objects.count(), 3)
