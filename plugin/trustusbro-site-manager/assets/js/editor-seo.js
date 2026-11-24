/**
 * TrustUsBro Site Manager — SEO panel for the block editor.
 *
 * Adds a compact sidebar panel so per-post SEO values can be edited next to the
 * article body. Stored in post meta and read by the SEO module (or passed to
 * Rank Math / Yoast when they are active).
 */
(function (wp) {
	'use strict';

	if (!wp || !wp.plugins || !wp.editPost || !wp.element || !wp.components) {
		return;
	}

	var el = wp.element.createElement;
	var Fragment = wp.element.Fragment;
	var registerPlugin = wp.plugins.registerPlugin;
	var PluginDocumentSettingPanel = wp.editPost.PluginDocumentSettingPanel;
	var TextControl = wp.components.TextControl;
	var TextareaControl = wp.components.TextareaControl;
	var ToggleControl = wp.components.ToggleControl;
	var MediaUpload = wp.blockEditor && wp.blockEditor.MediaUpload;
	var MediaUploadCheck = wp.blockEditor && wp.blockEditor.MediaUploadCheck;
	var useSelect = wp.data.useSelect;
	var useDispatch = wp.data.useDispatch;
	var __ = wp.i18n.__;

	function SeoPanel() {
		var meta = useSelect(function (select) {
			return select('core/editor').getEditedPostAttribute('meta') || {};
		}, []);
		var editPost = useDispatch('core/editor').editPost;

		function setMeta(key, value) {
			var next = Object.assign({}, meta);
			next[key] = value;
			editPost({ meta: next });
		}

		var imageId = meta._tusb_seo_og_image || 0;
		var image = useSelect(function (select) {
			return imageId ? select('core').getMedia(imageId) : null;
		}, [imageId]);

		var title = meta._tusb_seo_title || '';
		var description = meta._tusb_seo_description || '';

		return el(
			PluginDocumentSettingPanel,
			{
				name: 'tusb-seo',
				title: __('SEO (TrustUsBro)', 'trustusbro-site-manager'),
				className: 'tusb-seo-panel'
			},
			el(
				Fragment,
				null,
				el(TextControl, {
					label: __('SEO title', 'trustusbro-site-manager'),
					help: __('Leave empty to use the post title. Recommended: under 60 characters.', 'trustusbro-site-manager'),
					value: title,
					maxLength: 70,
					onChange: function (value) { setMeta('_tusb_seo_title', value); }
				}),
				el(TextareaControl, {
					label: __('Meta description', 'trustusbro-site-manager'),
					help: __('Recommended: 120–155 characters. Leave empty to use the excerpt.', 'trustusbro-site-manager'),
					value: description,
					maxLength: 180,
					onChange: function (value) { setMeta('_tusb_seo_description', value); }
				}),
				el(TextControl, {
					label: __('Canonical URL', 'trustusbro-site-manager'),
					help: __('Only set this if this content duplicates another page. Leave empty for normal behaviour.', 'trustusbro-site-manager'),
					type: 'url',
					value: meta._tusb_seo_canonical || '',
					onChange: function (value) { setMeta('_tusb_seo_canonical', value); }
				}),
				el(ToggleControl, {
					label: __('Exclude from search engines', 'trustusbro-site-manager'),
					checked: Boolean(meta._tusb_seo_noindex),
					onChange: function (value) { setMeta('_tusb_seo_noindex', value); }
				}),
				MediaUploadCheck && MediaUpload ? el(
					MediaUpload,
					{
						onSelect: function (media) { setMeta('_tusb_seo_og_image', media.id); },
						allowedTypes: ['image'],
						value: imageId,
						render: function (obj) {
							return el('div', { className: 'tusb-seo-image' },
								image && image.source_url ? el('img', { src: image.source_url, alt: '', style: { maxWidth: '100%', height: 'auto', marginBottom: '8px' } }) : null,
								el(wp.components.Button, { variant: 'secondary', onClick: obj.open }, imageId ? __('Replace social image', 'trustusbro-site-manager') : __('Choose social image', 'trustusbro-site-manager')),
								imageId ? el(wp.components.Button, { variant: 'link', isDestructive: true, onClick: function () { setMeta('_tusb_seo_og_image', 0); } }, __('Remove', 'trustusbro-site-manager')) : null
							);
						}
					}
				) : null
			)
		);
	}

	registerPlugin('tusb-seo-panel', { render: SeoPanel });
})(window.wp);
