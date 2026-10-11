"""Панель управления /admin/: вход, адреса, разделы и альбомы, тексты, перенос фото."""

import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from ..models import Album, Photo, Section


@override_settings(SECURE_SSL_REDIRECT=False)
class ManageTests(TestCase):
    """«Управление» вместо админки Django: порядок, скрытие, создание, тексты альбома, перенос фото."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user('staff', is_staff=True)
        cls.travel = Section.objects.create(name='Путешествия', slug='puteshestviya', order=0)
        cls.walks = Section.objects.create(name='Прогулки', slug='progulki', order=1)
        cls.bali = Album.objects.create(section=cls.travel, name='Бали', order=0)
        cls.china = Album.objects.create(section=cls.travel, name='Китай', order=1)
        cls.moscow = Album.objects.create(section=cls.walks, name='Москва', order=0)

        def photo(title, cat, album):
            return Photo(
                title=title, section=cat, album=album, image=f'photos/t/{title}.jpg', thumb=f'thumbs/t/{title}_t.jpg'
            )

        Photo.objects.bulk_create(
            [photo('b1', cls.travel, cls.bali), photo('b2', cls.travel, cls.bali), photo('c1', cls.travel, cls.china)]
        )
        cls.b1, cls.b2 = Photo.objects.get(title='b1'), Photo.objects.get(title='b2')
        cls.bali.cover = cls.b1
        cls.bali.save()

    def setUp(self):
        self.client.force_login(self.staff)

    def post(self, view, **data):
        return self.client.post(reverse('panel:' + view.removeprefix('manage_')), data)

    def test_only_for_staff(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('panel:albums')).status_code, 302)
        self.assertEqual(self.post('manage_toggle', kind='album', id=self.bali.pk, hidden='1').status_code, 302)
        self.assertEqual(self.post('move_photos', ids=self.b1.pk, album=self.china.pk).status_code, 302)
        self.bali.refresh_from_db()
        self.assertFalse(self.bali.hidden)

    def test_page_lists_sections_and_albums(self):
        self.china.hidden = True  # скрытый альбом в списке есть и помечен (не прячется, как кадры .is-hidden)
        self.china.save()
        r = self.client.get(reverse('panel:albums'))
        self.assertContains(
            r, 'class="mg-album js-row mg-off" data-kind="album" data-id="%d"' % self.china.pk, html=False
        )
        for text in (
            'Путешествия',
            'Прогулки',
            'Бали',
            'Китай',
            'Москва',
            reverse('panel:album_texts', args=[self.bali.pk]),
        ):
            self.assertContains(r, text)

    def test_order_of_albums_and_sections(self):
        r = self.post('manage_order', kind='album', section=self.travel.pk, ids=[self.china.pk, self.bali.pk])
        self.assertEqual(r.json(), {'ok': True})
        self.assertEqual([a.name for a in self.travel.albums.all()], ['Китай', 'Бали'])
        self.post('manage_order', kind='section', ids=[self.walks.pk, self.travel.pk])
        self.assertEqual([c.name for c in Section.objects.all()], ['Прогулки', 'Путешествия'])
        # неполный список или чужой альбом — отказ, порядок не трогаем
        self.assertEqual(
            self.post('manage_order', kind='album', section=self.travel.pk, ids=[self.bali.pk]).status_code, 409
        )
        self.assertEqual(
            self.post(
                'manage_order', kind='album', section=self.travel.pk, ids=[self.bali.pk, self.moscow.pk]
            ).status_code,
            409,
        )

    def test_toggle_hidden(self):
        self.assertTrue(self.post('manage_toggle', kind='album', id=self.bali.pk, hidden='1').json()['hidden'])
        self.client.logout()
        self.assertEqual(self.client.get(reverse('album', args=[self.bali.pk])).status_code, 404)

    def test_rename_keeps_section_address(self):
        self.assertEqual(self.post('manage_rename', kind='album', id=self.bali.pk, name='   ').status_code, 400)
        self.assertEqual(self.post('manage_rename', kind='album', id=self.bali.pk, name='x' * 201).status_code, 400)
        self.assertEqual(
            self.post('manage_rename', kind='section', id=self.travel.pk, name='  Поездки  ').json()['name'], 'Поездки'
        )
        self.travel.refresh_from_db()
        self.assertEqual((self.travel.name, self.travel.slug), ('Поездки', 'puteshestviya'))

    def test_create_hidden_at_the_end(self):
        album = Album.objects.get(
            pk=self.post('manage_create', kind='album', section=self.travel.pk, name='Тайланд').json()['id']
        )
        self.assertEqual((album.section, album.order, album.hidden), (self.travel, 2, True))
        cat = Section.objects.get(pk=self.post('manage_create', kind='section', name='Новый раздел').json()['id'])
        self.assertEqual((cat.slug, cat.order, cat.hidden), ('novyy-razdel', 2, True))
        again = Section.objects.get(pk=self.post('manage_create', kind='section', name='Новый раздел').json()['id'])
        self.assertEqual(again.slug, 'novyy-razdel-2')
        self.assertEqual(self.post('manage_create', kind='album', section=999, name='X').status_code, 404)

    def test_delete_only_empty(self):
        self.assertEqual(self.post('manage_delete', kind='album', id=self.bali.pk).status_code, 400)
        self.assertEqual(self.post('manage_delete', kind='section', id=self.travel.pk).status_code, 400)
        empty = Album.objects.create(section=self.walks, name='Пустой')
        self.assertTrue(self.post('manage_delete', kind='album', id=empty.pk).json()['ok'])
        self.assertFalse(Album.objects.filter(pk=empty.pk).exists())

    def test_album_texts(self):
        url = reverse('panel:album_texts', args=[self.bali.pk])
        self.assertContains(self.client.get(url), 'Так будет на странице альбома')
        r = self.client.post(
            url,
            {
                'name': ' Бали ',
                'section': self.travel.pk,
                'place': '  Индонезия ',
                'period': 'декабрь 2024',
                'intro': 'Коротко.',
                'description': 'Раз.\r\n\r\nДва.\r\n',
                'gear': 'Fujifilm X100VI',
            },
        )
        self.assertRedirects(r, url)
        self.bali.refresh_from_db()
        self.assertEqual(
            (self.bali.name, self.bali.place, self.bali.description, self.bali.hidden),
            ('Бали', 'Индонезия', 'Раз.\n\nДва.', False),
        )
        r = self.client.post(url, {'name': '  ', 'section': self.travel.pk})
        self.assertEqual(r.status_code, 200)  # пустое название — форма с ошибкой, ничего не сохраняем
        self.bali.refresh_from_db()
        self.assertEqual(self.bali.name, 'Бали')

    def test_album_moves_to_other_section_with_its_photos(self):
        self.travel.cover = self.b1
        self.travel.save()
        self.client.post(reverse('panel:album_texts', args=[self.bali.pk]), {'name': 'Бали', 'section': self.walks.pk})
        self.assertEqual(set(Photo.objects.filter(album=self.bali).values_list('section', flat=True)), {self.walks.pk})
        self.travel.refresh_from_db()
        self.assertIsNone(self.travel.cover)

    def test_move_photos_between_albums(self):
        d = self.post('move_photos', ids=[self.b1.pk], album=self.moscow.pk).json()
        self.assertEqual((d['moved'], d['album']), (1, 'Москва'))
        self.b1.refresh_from_db()
        self.bali.refresh_from_db()
        self.assertEqual((self.b1.album, self.b1.section), (self.moscow, self.walks))
        self.assertIsNone(self.bali.cover)  # обложка уехала из альбома — сброшена
        self.assertEqual(self.post('move_photos', ids=[self.b2.pk], album=999).status_code, 404)
        self.assertEqual(self.post('move_photos', album=self.china.pk).status_code, 400)

    def test_menu_and_move_control_for_staff_only(self):
        r = self.client.get(reverse('album', args=[self.bali.pk]))
        self.assertContains(r, 'href="%s"' % reverse('panel:albums'), html=False)
        self.assertContains(r, '<option value="%d">Китай</option>' % self.china.pk, html=False)
        self.assertNotContains(r, '<option value="%d">' % self.bali.pk, html=False)  # в свой же альбом — нет
        self.client.logout()
        r = self.client.get(reverse('album', args=[self.bali.pk]))
        self.assertNotContains(r, 'href="%s"' % reverse('panel:albums'), html=False)
        self.assertNotContains(r, 'class="move-target js-move-target"', html=False)


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminAddressTests(TestCase):
    """08.10.2026: /admin/ — наша панель со своей страницей входа, /admindjango/ — панель Django."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_user(
            'roman', password='верный-пароль-123', is_staff=True, is_superuser=True
        )

    def setUp(self):
        self.counters = tempfile.TemporaryDirectory()  # свои счётчики входов у каждого теста
        self.addCleanup(self.counters.cleanup)
        self.enterContext(override_settings(LOGIN_COUNTERS_DIR=self.counters.name))

    def test_admin_without_login_shows_our_login_page(self):
        r = self.client.get('/admin/', follow=True)
        self.assertEqual(
            r.redirect_chain, [('/admin/login/?next=/admin/', 302)]
        )  # сразу на свой вход, без промежуточного шага
        self.assertContains(r, 'своя панель управления')
        self.assertContains(r, 'id="id_password"', html=False)
        self.assertContains(r, 'Обо мне')  # страница в оформлении сайта, с его шапкой и меню

    def test_login_leads_to_our_panel(self):
        r = self.client.post('/admin/login/', {'username': 'roman', 'password': 'верный-пароль-123', 'next': '/admin/'})
        self.assertRedirects(r, '/admin/')
        self.assertContains(self.client.get('/admin/'), 'Альбомы')

    def test_django_panel_moved_and_uses_our_login(self):
        r = self.client.get('/admindjango/', follow=True)
        self.assertEqual(r.redirect_chain[-1][0], '/admin/login/?next=%2Fadmindjango%2F')
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/admindjango/').status_code, 200)

    def test_menu_links_and_logout(self):
        self.client.force_login(self.admin)
        r = self.client.get('/')
        self.assertContains(r, 'href="/admin/"', html=False)
        self.assertContains(r, 'href="/admindjango/"', html=False)
        self.client.post('/admin/logout/')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_old_addresses_redirect(self):
        for old, new in (
            ('/photos/manage/', '/admin/'),
            ('/photos/manage/album/5/', '/admin/album/5/'),
            ('/photos/upload/', '/admin/upload/'),
            ('/photos/trash/', '/admin/trash/'),
            ('/photos/stats/', '/admin/disk/'),
        ):
            self.assertRedirects(self.client.get(old), new, fetch_redirect_response=False)

    def test_robots_hides_both_panels(self):
        r = self.client.get('/robots.txt').content.decode()
        self.assertIn('Disallow: /admin/', r)
        self.assertIn('Disallow: /admindjango/', r)


@override_settings(SECURE_SSL_REDIRECT=False)
class DjangoAdminPhotoTests(TestCase):
    """Аудит 2: в запасной панели Django нет загрузки файлов фото — значит, нет и разбора в обход проверки."""

    def test_no_file_upload_in_django_admin(self):
        from ..models import Photo

        admin_user = get_user_model().objects.create_user('roman', is_staff=True, is_superuser=True)
        self.client.force_login(admin_user)
        self.assertEqual(self.client.get('/admindjango/photos/photo/add/').status_code, 403)
        section = Section.objects.create(name='Р', slug='r')
        photo = Photo.objects.create(title='kadr', section=section, image='photos/x.jpg')
        page = self.client.get('/admindjango/photos/photo/%d/change/' % photo.pk).content.decode()
        self.assertNotIn('type="file"', page)
