"""验证 GPT 生图档位转换及上游返回尺寸，不调用实际生图接口。"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from core.aspect_ratios import IMAGE_ASPECT_RATIOS, normalize_parameters, provider_parameters
from workers.output_dimensions import check_dimensions


MODELS = ('gpt-image-2', 'gpt-image-2.5-flare', 'gpt-image-2.5-sunburst')


class ImageResolutionTest(unittest.TestCase):
    def test_landscape_tiers_for_all_three_models(self):
        for model in MODELS:
            for resolution, size in (('1K', '1536x864'), ('2K', '2048x1152'), ('4K', '3840x2160')):
                parameters = {'aspect_ratio': '16:9', 'image_size': resolution, 'quality': 'high'}
                with self.subTest(model=model, resolution=resolution):
                    self.assertEqual(provider_parameters('image', 'openai', model, parameters),
                                     {'size': size, 'quality': 'high'})
                    self.assertEqual(parameters['image_size'], resolution)

    def test_all_presets_meet_provider_constraints(self):
        for ratio in IMAGE_ASPECT_RATIOS:
            if ratio == 'auto':
                continue
            pixels = []
            for resolution in ('1K', '2K', '4K'):
                with self.subTest(ratio=ratio, resolution=resolution):
                    result = provider_parameters('image', 'openai', MODELS[0],
                                                 {'aspect_ratio': ratio, 'image_size': resolution})
                    width, height = map(int, result['size'].split('x'))
                    ratio_width, ratio_height = map(int, ratio.split(':'))
                    self.assertEqual(width * ratio_height, height * ratio_width)
                    self.assertEqual(width % 16, 0)
                    self.assertEqual(height % 16, 0)
                    self.assertLessEqual(max(width, height), 3840)
                    self.assertLessEqual(max(width, height), 3 * min(width, height))
                    self.assertTrue(655360 <= width * height <= 8294400)
                    pixels.append(width * height)
            self.assertTrue(pixels[0] < pixels[1] < pixels[2])

    def test_auto_and_legacy_requests(self):
        for parameters in ({'aspect_ratio': '16:9'}, {'size': '1536x864'},
                           {'aspect_ratio': '16:9', 'image_size': 'auto'}):
            self.assertEqual(provider_parameters('image', 'openai', MODELS[0], parameters),
                             {'size': '1536x864'})
        self.assertEqual(provider_parameters('image', 'openai', MODELS[0],
                                             {'aspect_ratio': 'auto', 'image_size': 'auto'}), {'size': 'auto'})
        for resolution in ('1K', '2K', '4K'):
            with self.assertRaisesRegex(ValueError, '自动比例'):
                provider_parameters('image', 'openai', MODELS[0],
                                    {'aspect_ratio': 'auto', 'image_size': resolution})

    def test_unsupported_tiers_and_models_are_rejected(self):
        for resolution in ('512px', '8K', '', 2048):
            with self.assertRaisesRegex(ValueError, '分辨率档位'):
                provider_parameters('image', 'openai', MODELS[0],
                                    {'aspect_ratio': '1:1', 'image_size': resolution})
        with self.assertRaisesRegex(ValueError, '不支持分辨率档位'):
            provider_parameters('image', 'openai', 'gpt-image-1',
                                {'aspect_ratio': '1:1', 'image_size': '4K'})

    def test_history_keeps_selected_tier(self):
        parameters = {'aspect_ratio': '9:16', 'image_size': '4K', 'quality': 'high'}
        restored = normalize_parameters('image', parameters)
        self.assertEqual(restored, parameters)
        self.assertEqual(provider_parameters('image', 'openai', MODELS[0], restored)['size'], '2160x3840')

    def test_gemini_and_video_parameters_are_unchanged(self):
        self.assertEqual(provider_parameters('image', 'gemini', 'gemini-3.1-flash-image-preview',
                                             {'aspect_ratio': '16:9', 'image_size': '4K', 'quality': 'high'}),
                         {'aspect_ratio': '16:9', 'image_size': '4K'})
        self.assertEqual(provider_parameters('video', 'ark', 'seedance',
                                             {'aspect_ratio': '16:9', 'resolution': '1080p'}),
                         {'ratio': '16:9', 'resolution': '1080p'})

    def test_same_ratio_with_wrong_resolution_is_reported(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'image.png'
            Image.new('RGB', (1536, 864)).save(path)
            result = check_dimensions('test', path, '16:9', expected_size='3840x2160')
            self.assertEqual((result['width'], result['height']), (1536, 864))
            self.assertIn('3840×2160', result['warning'])
            self.assertIn('1536×864', result['warning'])
            self.assertNotIn('warning', check_dimensions('test', path, '16:9', expected_size='1536x864'))
            self.assertNotIn('warning', check_dimensions('test', path, 'auto', expected_size='auto'))


if __name__ == '__main__':
    unittest.main()
