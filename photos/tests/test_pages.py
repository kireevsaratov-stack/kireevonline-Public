"""Публичные страницы: главная, разделы, альбомы, «Обо мне», «Барабан», старые адреса."""

import re

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from ..models import Album, Photo, Section


@override_settings(SECURE_SSL_REDIRECT=False)
class PublicSiteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cat = Section.objects.create(name='Путешествия', slug='puteshestviya')
        cls.album = Album.objects.create(section=cat, name='Бали', description='Остров, храмы и океан.')
        cls.hidden = Album.objects.create(section=cat, name='Алтай', hidden=True)
        cls.staff = get_user_model().objects.create_user('staff', is_staff=True)

    def test_home_opens_at_root_with_canonical(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Киреев Роман')
        self.assertContains(r, '<link rel="canonical" href="https://kireevonline.ru/">', html=False)

    def test_home_screen_icon_for_iphone(self):
        """«На экран Домой» на iPhone: свой значок 180×180 и короткое имя под ним."""
        from django.contrib.staticfiles import finders
        from PIL import Image

        r = self.client.get('/')
        self.assertContains(r, '<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">', html=False)
        self.assertContains(r, '<meta name="apple-mobile-web-app-title" content="Киреев">', html=False)
        with Image.open(finders.find('apple-touch-icon.png')) as icon:
            self.assertEqual((icon.format, icon.size), ('PNG', (180, 180)))

    def test_old_photos_address_still_works_without_redirect_loop(self):
        r = self.client.get('/photos/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '<link rel="canonical" href="https://kireevonline.ru/">', html=False)

    def test_about_page(self):
        r = self.client.get('/about/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Leica Q3')
        self.assertContains(r, 'фотодневник')

    def test_menu_has_about_and_hides_admin_from_visitors(self):
        r = self.client.get('/')
        self.assertContains(r, 'href="/about/"')
        self.assertNotContains(r, 'href="/admin/"')
        self.client.force_login(self.staff)
        self.assertContains(self.client.get('/'), 'href="/admin/"')

    def test_hidden_album_is_404_for_visitors_and_open_for_staff(self):
        url = '/album/%d/' % self.hidden.pk
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_album_description_goes_to_meta_description(self):
        r = self.client.get('/album/%d/' % self.album.pk)
        self.assertContains(r, '<meta name="description" content="Остров, храмы и океан.">', html=False)

    def test_album_intro_with_plus_revealing_full_text_and_gear(self):
        album = Album.objects.create(
            section=self.album.section,
            name='Китай',
            intro='Пекин зимой.',
            description='Подробный рассказ.',
            gear='Fujifilm X-T5',
        )
        r = self.client.get('/album/%d/' % album.pk)
        self.assertContains(r, '<p class="album-intro-text">Пекин зимой.', html=False)
        self.assertContains(r, 'class="album-intro-more js-intro-toggle"')
        self.assertContains(r, '<meta name="description" content="Пекин зимой.">', html=False)
        # подробный текст спрятан под «+», а строка «Снято на» видна всегда — она вне спрятанного
        html = r.content.decode()
        hidden = re.search(r'<div class="album-intro-full" id="album-intro-full">.*?</div>\s*</div>', html, re.S)
        self.assertIn('Подробный рассказ.', hidden.group(0))
        self.assertNotIn('album-gear', hidden.group(0))
        self.assertGreater(html.index('<p class="album-gear">Снято на Fujifilm\u00a0X-T5</p>'), hidden.end() - 1)

    def test_album_place_and_period_in_header_and_notes_split_into_paragraphs(self):
        album = Album.objects.create(
            section=self.album.section,
            name='Китай',
            place='Пекин, Китай',
            period='январь 2025',
            intro='Пекин зимой.',
            description='Первый абзац.\n\nВторой абзац.',
        )
        r = self.client.get('/album/%d/' % album.pk)
        self.assertContains(r, 'Пекин, Китай · январь 2025 · 0 фото')
        self.assertContains(r, '<p>Первый абзац.</p>', html=False)
        self.assertContains(r, '<p>Второй абзац.</p>', html=False)
        r = self.client.get('/album/%d/' % self.album.pk)  # без места и времени — только число фото
        self.assertContains(r, '<p class="section-count">0 фото</p>', html=False)

    def test_dash_never_starts_a_line_and_text_stays_escaped(self):
        album = Album.objects.create(
            section=self.album.section,
            name='Китай',
            intro='Пекин — зимой.',
            description='Стена — длинная. <b>не тег</b>',
        )
        r = self.client.get('/album/%d/' % album.pk)
        self.assertContains(r, 'Пекин — зимой.')
        self.assertContains(r, 'Стена — длинная.')
        self.assertContains(r, '&lt;b&gt;не тег&lt;/b&gt;', html=False)

    def test_each_camera_gets_its_own_gear_line(self):
        album = Album.objects.create(
            section=self.album.section,
            name='Дрифт',
            gear='Canon EOS R6 Mark II + RF 135mm; Sony A7R V + FE 50mm, FE 35mm',
        )
        r = self.client.get('/album/%d/' % album.pk)
        self.assertContains(
            r,
            '<p class="album-gear">Снято на Canon\u00a0EOS\u00a0R6\u00a0Mark\u00a0II + RF\u00a0135mm<br>'
            'Sony\u00a0A7R\u00a0V + FE\u00a050mm + FE\u00a035mm</p>',
            html=False,
        )

    def test_no_plus_when_nothing_is_hidden(self):
        with_gear = Album.objects.create(
            section=self.album.section, name='Питер', intro='Каяки и музеи.', gear='Leica Q3'
        )
        r = self.client.get('/album/%d/' % with_gear.pk)
        self.assertContains(r, '<p class="album-gear">Снято на Leica\u00a0Q3</p>', html=False)
        self.assertNotContains(r, 'class="album-intro-more js-intro-toggle"')
        self.assertNotContains(r, 'id="album-intro-full"')
        intro_only = Album.objects.create(section=self.album.section, name='Питер 2', intro='Каяки и музеи.')
        r = self.client.get('/album/%d/' % intro_only.pk)
        self.assertContains(r, 'Каяки и музеи.')
        self.assertNotContains(r, 'class="album-intro-more js-intro-toggle"')

    def test_custom_404_page(self):
        r = self.client.get('/net-takoy-stranicy/')
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, 'Здесь пусто', status_code=404)

    def test_hidden_section_disappears_for_visitors_and_staff_opens_it_from_manage(self):
        cat = Section.objects.create(name='Портреты', slug='portrety', hidden=True)
        album = Album.objects.create(section=cat, name='Портреты')
        home = self.client.get('/').content.decode()
        self.assertNotIn('Портреты', home)  # ни в меню, ни в кнопках, ни в карточках
        self.assertEqual(self.client.get('/section/portrety/').status_code, 404)
        self.assertEqual(self.client.get('/album/%d/' % album.pk).status_code, 404)
        sitemap = self.client.get('/sitemap.xml').content.decode()
        self.assertNotIn('/section/portrety/', sitemap)
        self.assertNotIn('/album/%d/' % album.pk, sitemap)
        # админ видит сайт как гость (Роман, 03.10.2026): скрытого нет ни в меню, ни на главной…
        self.client.force_login(self.staff)
        self.assertNotIn('Портреты', self.client.get('/').content.decode())
        # …а открывает его из «Админ → Альбомы», и на странице видно, что оно скрыто
        self.assertContains(self.client.get('/admin/'), 'href="/section/portrety/"', html=False)
        self.assertContains(self.client.get('/section/portrety/'), 'Раздел скрыт от посетителей')
        self.assertContains(self.client.get('/album/%d/' % album.pk), 'Скрыт от посетителей')

    def test_staff_sees_public_lists_like_a_visitor(self):
        hidden = Album.objects.create(section=self.album.section, name='Тайное', hidden=True)
        Photo.objects.create(
            title='p', section=self.album.section, album=self.album, image='photos/t/p.jpg', thumb='thumbs/t/p_t.jpg'
        )
        Photo.objects.create(
            title='h', section=self.album.section, album=hidden, image='photos/t/h.jpg', thumb='thumbs/t/h_t.jpg'
        )
        self.client.force_login(self.staff)
        for url in ('/', '/section/puteshestviya/', '/album/%d/' % self.album.pk):
            html = self.client.get(url).content.decode()
            self.assertNotIn('Тайное', html.split('class="move-target')[0], url)  # кроме служебного «Перенести в…»
        self.assertNotIn('thumbs/t/h_t.jpg', self.client.get('/shuffle/').content.decode())
        # в служебном «Перенести в альбом…» скрытый альбом есть — туда можно переносить
        self.assertContains(
            self.client.get('/album/%d/' % self.album.pk),
            '<option value="%d">Тайное ·</option>' % hidden.pk,
            html=False,
        )

    def test_sitemap_lists_about_and_skips_hidden_album(self):
        body = self.client.get('/sitemap.xml').content.decode()
        self.assertIn('/about/', body)
        self.assertIn('/album/%d/' % self.album.pk, body)
        self.assertNotIn('/album/%d/' % self.hidden.pk, body)


@override_settings(SECURE_SSL_REDIRECT=False)
class ThumbBatchTests(TestCase):
    """Адрес превью сразу — только у первых 40 кадров, у остальных data-src: иначе браузер разом
    просит у сервера все превью (02.10 на «Барабане» — 2429 запросов, сервер отказывал)."""

    @classmethod
    def setUpTestData(cls):
        cat = Section.objects.create(name='Путешествия', slug='puteshestviya')
        cls.album = Album.objects.create(section=cat, name='Бали')
        Photo.objects.bulk_create(
            [
                Photo(
                    title=f'p{i}',
                    section=cat,
                    album=cls.album,
                    image=f'photos/t/p{i}.jpg',
                    thumb=f'thumbs/t/p{i}_t.jpg',
                )
                for i in range(45)
            ]
        )

    def assert_first_40_have_src(self, url):
        html = self.client.get(url).content.decode()
        self.assertEqual(len(re.findall(r'<img src="/media/thumbs/t/p\d+_t\.jpg"', html)), 40)
        self.assertEqual(len(re.findall(r'<img data-src="/media/thumbs/t/p\d+_t\.jpg"', html)), 5)

    def test_album(self):
        self.assert_first_40_have_src('/album/%d/' % self.album.pk)

    def test_shuffle(self):
        self.assert_first_40_have_src('/shuffle/')


@override_settings(SECURE_SSL_REDIRECT=False)
class ShuffleTests(TestCase):
    """«Барабан»: все фото, видимые гостю, вперемешку, как альбом; в просмотре — ссылка на альбом кадра."""

    @classmethod
    def setUpTestData(cls):
        open_cat = Section.objects.create(name='Путешествия', slug='puteshestviya')
        hidden_cat = Section.objects.create(name='Портреты', slug='portrety', hidden=True)
        cls.album = Album.objects.create(section=open_cat, name='Бали')
        hidden_album = Album.objects.create(section=open_cat, name='Алтай', hidden=True)

        def photo(title, cat, album=None, deleted=False):
            return Photo(
                title=title,
                section=cat,
                album=album,
                is_deleted=deleted,
                image=f'photos/t/{title}.jpg',
                thumb=f'thumbs/t/{title}_t.jpg',
            )

        Photo.objects.bulk_create(
            [photo(f'vis{i}', open_cat, cls.album) for i in range(5)]
            + [
                photo('loose', open_cat),  # фото без альбома — ведёт в раздел
                photo('hiddenalbum', open_cat, hidden_album),
                photo('hiddencat', hidden_cat),
                photo('deleted', open_cat, cls.album, deleted=True),
            ]
        )

    def test_shows_every_visible_photo_like_an_album_with_album_links(self):
        r = self.client.get('/shuffle/')
        html = r.content.decode()
        self.assertEqual(html.count('class="photo-item'), 6)
        for hidden in ('hiddenalbum', 'hiddencat', 'deleted'):
            self.assertNotIn('/' + hidden, html)
        self.assertIn('data-album="/album/%d/"' % self.album.pk, html)
        self.assertIn('data-album="/section/puteshestviya/"', html)
        self.assertContains(r, 'class="view-btn js-view-feed"')
        self.assertContains(r, 'class="slot js-spin"')  # кнопка «Вращайте барабан»
        self.assertContains(r, 'id="lb-album"')  # в просмотре — «Перейти к альбому»
        self.assertContains(r, 'Крути в&nbsp;своё удовольствие, правда, призов здесь не', html=False)
        self.assertContains(r, '<meta name="robots" content="noindex">', html=False)

    def test_home_and_menu_link_to_baraban_without_slot(self):
        r = self.client.get('/')
        self.assertContains(r, '<a class="filter-chip" href="/shuffle/">Барабан</a>', html=False)  # в строке разделов
        self.assertContains(r, 'href="/shuffle/">Барабан</a>', count=2, html=False)  # и в меню
        self.assertNotContains(r, 'class="slot')


@override_settings(SECURE_SSL_REDIRECT=False)
class LegacyAddressTests(TestCase):
    """08.10.2026: страницы переехали на /section/…, /album/…, /shuffle/.
    Старые ссылки (поисковики, закладки) ведут туда."""

    def test_old_public_addresses_redirect_permanently(self):
        for old, new in (
            ('/photos/category/reportazh/', '/section/reportazh/'),
            ('/photos/subcategory/41/', '/album/41/'),
            ('/photos/shuffle/', '/shuffle/'),
        ):
            r = self.client.get(old)
            self.assertEqual((r.status_code, r['Location']), (301, new), old)

    def test_photos_still_opens_home_without_redirect(self):
        """Когда-то «/» навсегда вёл на /photos/ — браузеры это помнят; редирект обратно дал бы петлю."""
        self.assertEqual(self.client.get('/photos/').status_code, 200)
