/**
 * TrustUsBro Site Manager — dashboard application.
 *
 * Deliberately dependency-light (no build step): plain ES5-compatible DOM code
 * with the WP REST API. Requirements:
 *  - every screen is keyboard operable (no drag-only paths)
 *  - every destructive action confirms, and offers undo where possible
 *  - saving and publishing are separate, explicit steps
 */
(function () {
	'use strict';

	var T = window.TUSB || {};
	var app = document.getElementById('tusb-app');
	if (!app) {
		return;
	}

	var state = {
		boot: null,
		view: app.getAttribute('data-view') || 'dashboard',
		doc: app.getAttribute('data-doc') || '',
		docs: {},          // docKey -> {schema, draft, published, meta, revisions...}
		draft: null,       // in-memory working copy of the open document
		draftDoc: '',      // which document state.draft belongs to
		dirty: false,
		saving: false,
		selectedSection: null,
		collapsed: {},
		toastTimer: null,
		lastUndo: null
	};

	/* ------------------------------------------------------------------
	 * Utilities
	 * ------------------------------------------------------------------ */

	function el(tag, attrs, children) {
		var node = document.createElement(tag);
		if (attrs) {
			Object.keys(attrs).forEach(function (key) {
				var value = attrs[key];
				if (value === null || value === undefined || value === false) {
					return;
				}
				if (key === 'class') {
					node.className = value;
				} else if (key === 'text') {
					node.textContent = value;
				} else if (key === 'html') {
					node.innerHTML = value;
				} else if (key.indexOf('on') === 0 && typeof value === 'function') {
					node.addEventListener(key.slice(2).toLowerCase(), value);
				} else if (key === 'dataset') {
					Object.keys(value).forEach(function (dataKey) {
						node.setAttribute('data-' + dataKey, value[dataKey]);
					});
				} else if (value === true) {
					node.setAttribute(key, '');
				} else {
					node.setAttribute(key, value);
				}
			});
		}
		(children || []).forEach(function (child) {
			if (child === null || child === undefined || child === false) {
				return;
			}
			node.appendChild(typeof child === 'string' || typeof child === 'number' ? document.createTextNode(String(child)) : child);
		});
		return node;
	}

	function $(selector, root) {
		return (root || document).querySelector(selector);
	}

	function $$(selector, root) {
		return Array.prototype.slice.call((root || document).querySelectorAll(selector));
	}

	function clone(value) {
		return JSON.parse(JSON.stringify(value === undefined ? null : value));
	}

	function t(key) {
		var strings = {
			save: 'Save draft',
			saving: 'Saving…',
			saved: 'Draft saved',
			publish: 'Publish changes',
			publishing: 'Publishing…',
			published: 'Published — your website is updated',
			discard: 'Discard draft changes',
			preview: 'Preview',
			undo: 'Undo',
			delete: 'Delete',
			duplicate: 'Duplicate',
			add: 'Add',
			remove: 'Remove',
			moveUp: 'Move up',
			moveDown: 'Move down',
			somethingWrong: 'Something went wrong. Your changes are still in this browser — please try again.',
			nothingToPublish: 'There is nothing new to publish.',
			confirmDeleteSection: 'Remove this section from the page? You can undo this from Revision history.',
			confirmDeleteItem: 'Delete this item? This cannot be undone once you publish.',
			confirmDiscard: 'Discard all unpublished changes for this screen?',
			confirmRestore: 'Restore this version? Your current draft will be replaced. The live site will not change until you publish.',
			thisNeedsPublish: 'Saved as a draft. Use "Publish changes" to update the live site.',
			editHint: 'Click any text to edit it directly.'
		};
		return strings[key] || key;
	}

	function api(path, options) {
		options = options || {};
		var url = String(T.restUrl || '/wp-json/tusb/v1/');
		if (url.charAt(url.length - 1) !== '/') {
			url += '/';
		}
		url += String(path).replace(/^\/+/, '');
		var config = {
			method: options.method || 'GET',
			headers: {
				'X-WP-Nonce': T.nonce
			},
			credentials: 'same-origin'
		};
		if (options.body) {
			config.headers['Content-Type'] = 'application/json';
			config.body = JSON.stringify(options.body);
		}
		return fetch(url, config).then(function (response) {
			return response.json().then(function (json) {
				if (!response.ok) {
					var message = (json && json.message) || t('somethingWrong');
					var error = new Error(message);
					error.data = json;
					error.status = response.status;
					throw error;
				}
				return json;
			});
		});
	}

	function toast(message, type, action) {
		var existing = $('.tusb-toast');
		if (existing) {
			existing.parentNode.removeChild(existing);
		}
		var node = el('div', { class: 'tusb-toast tusb-toast--' + (type || 'info'), role: 'status', 'aria-live': 'polite' }, [
			el('span', { class: 'tusb-toast__text', text: message })
		]);
		if (action) {
			node.appendChild(el('button', {
				class: 'tusb-toast__action',
				type: 'button',
				text: action.label,
				onclick: function () {
					action.run();
					if (node.parentNode) {
						node.parentNode.removeChild(node);
					}
				}
			}));
		}
		node.appendChild(el('button', {
			class: 'tusb-toast__close',
			type: 'button',
			'aria-label': 'Dismiss',
			text: '×',
			onclick: function () {
				if (node.parentNode) {
					node.parentNode.removeChild(node);
				}
			}
		}));
		document.body.appendChild(node);
		window.clearTimeout(state.toastTimer);
		state.toastTimer = window.setTimeout(function () {
			if (node.parentNode) {
				node.parentNode.removeChild(node);
			}
		}, type === 'error' ? 9000 : 5000);
	}

	function spinner(label) {
		return el('div', { class: 'tusb-inline-loading' }, [
			el('span', { class: 'spinner is-active' }),
			el('span', { text: label || 'Loading…' })
		]);
	}

	function labelOf(key) {
		if (state.boot && state.boot.defaults && state.boot.defaults.doc_labels && state.boot.defaults.doc_labels[key]) {
			return state.boot.defaults.doc_labels[key];
		}
		return key.replace(/_/g, ' ');
	}

	/* ------------------------------------------------------------------
	 * Document loading & saving
	 * ------------------------------------------------------------------ */

	function loadDoc(docKey) {
		if (state.docs[docKey]) {
			return Promise.resolve(state.docs[docKey]);
		}
		return api('docs/' + encodeURIComponent(docKey)).then(function (data) {
			state.docs[docKey] = data;
			return data;
		});
	}

	function currentDoc() {
		return state.doc ? state.docs[state.doc] : null;
	}

	function syncDraftFromServer() {
		var doc = currentDoc();
		if (!doc) {
			return;
		}
		state.draft = clone(doc.draft);
		state.draftDoc = state.doc;
	}

	/**
	 * Make sure the in-memory draft matches the document being edited.
	 * Prevents edits from one screen leaking into another.
	 */
	function ensureDraft(docKey) {
		if (state.doc !== docKey) {
			state.doc = docKey;
		}
		if (!state.docs[docKey]) {
			return false;
		}
		if (!state.draft || state.draftDoc !== docKey) {
			state.draft = clone(state.docs[docKey].draft);
			state.draftDoc = docKey;
			state.dirty = false;
		}
		return true;
	}

	function markDirty() {
		state.dirty = true;
		updateSaveBar();
	}

	function saveDraft(options) {
		options = options || {};
		var doc = currentDoc();
		if (!doc || state.saving) {
			return Promise.resolve();
		}
		state.saving = true;
		updateSaveBar();
		return api('docs/' + encodeURIComponent(state.doc) + '/draft', {
			method: 'POST',
			body: { payload: state.draft, label: options.label || 'Edited in dashboard' }
		}).then(function (result) {
			state.saving = false;
			state.dirty = false;
			doc.draft = clone(state.draft);
			doc.meta = Object.assign({}, doc.meta, {
				draft_version: result.draft_version,
				published_version: result.published_version
			});
			doc.has_unpublished = result.has_unpublished;
			if (state.boot && state.boot.status[state.doc]) {
				state.boot.status[state.doc].has_unpublished = result.has_unpublished;
				state.boot.status[state.doc].draft_version = result.draft_version;
			}
			updateSaveBar();
			if (!options.silent) {
				if (result.has_unpublished) {
					toast(t('saved') + ' — ' + t('thisNeedsPublish'), 'success');
				} else {
					toast(t('saved'), 'success');
				}
			}
			return result;
		}).catch(function (error) {
			state.saving = false;
			updateSaveBar();
			toast(error.message || t('somethingWrong'), 'error');
			throw error;
		});
	}

	function publishDoc() {
		var doc = currentDoc();
		if (!doc || state.saving) {
			return;
		}
		state.saving = true;
		updateSaveBar();
		api('docs/' + encodeURIComponent(state.doc) + '/publish', {
			method: 'POST',
			body: state.dirty ? { payload: state.draft } : {}
		}).then(function (result) {
			state.saving = false;
			state.dirty = false;
			doc.published = result.published || doc.draft;
			doc.draft = clone(doc.published);
			doc.has_unpublished = false;
			if (state.boot && state.boot.status[state.doc]) {
				state.boot.status[state.doc].has_unpublished = false;
				state.boot.status[state.doc].published = true;
				state.boot.status[state.doc].published_at = result.published_at;
			}
			updateSaveBar();
			toast(t('published'), 'success');
			// Refresh revisions lazily next time the panel opens.
			doc.revisions = null;
		}).catch(function (error) {
			state.saving = false;
			updateSaveBar();
			toast(error.message || t('somethingWrong'), 'error');
		});
	}

	function discardDoc() {
		if (!window.confirm(t('confirmDiscard'))) {
			return;
		}
		api('docs/' + encodeURIComponent(state.doc) + '/discard', { method: 'POST' }).then(function (result) {
			var doc = currentDoc();
			doc.draft = result.draft;
			doc.has_unpublished = false;
			syncDraftFromServer();
			state.dirty = false;
			render();
			toast('Draft discarded — the published version is unchanged.', 'success');
		}).catch(function (error) {
			toast(error.message, 'error');
		});
	}

	/* ------------------------------------------------------------------
	 * Shell
	 * ------------------------------------------------------------------ */

	var NAV = [
		{ group: 'Home', items: [
			{ view: 'dashboard', label: 'Overview', icon: 'dashboard' },
			{ view: 'pages', label: 'Homepage & pages', icon: 'admin-page' }
		]},
		{ group: 'Content', items: [
			{ view: 'services', label: 'Services', icon: 'screenoptions' },
			{ view: 'industries', label: 'Industries', icon: 'building' },
			{ view: 'case_studies', label: 'Case studies', icon: 'portfolio' },
			{ view: 'testimonials', label: 'Testimonials', icon: 'format-quote' },
			{ view: 'faq', label: 'FAQ', icon: 'editor-help' },
			{ view: 'blog', label: 'Blog', icon: 'admin-post' }
		]},
		{ group: 'Layout', items: [
			{ view: 'header', label: 'Header', icon: 'align-center' },
			{ view: 'footer', label: 'Footer', icon: 'align-wide' },
			{ view: 'contact', label: 'Contact details', icon: 'email-alt' }
		]},
		{ group: 'Site', items: [
			{ view: 'design', label: 'Design settings', icon: 'art' },
			{ view: 'seo', label: 'SEO', icon: 'search' },
			{ view: 'media', label: 'Media', icon: 'format-image' },
			{ view: 'backups', label: 'Backups', icon: 'database' },
			{ view: 'revisions', label: 'Revision history', icon: 'backup' },
			{ view: 'health', label: 'Health & help', icon: 'sos' }
		]}
	];

	var VIEW_TO_DOC = {
		services: 'services',
		industries: 'industries',
		case_studies: 'case_studies',
		testimonials: 'testimonials',
		faq: 'faq',
		header: 'header',
		footer: 'footer',
		contact: 'contact',
		design: 'design'
	};

	function render() {
		app.innerHTML = '';
		app.appendChild(renderSidebar());
		saveBar = null;
		var main = el('main', { class: 'tusb-main', id: 'tusb-main' });
		main.appendChild(renderTopbar());
		var body = el('div', { class: 'tusb-body' });
		main.appendChild(body);
		app.appendChild(main);

		var view = state.view;
		if (view === 'dashboard') {
			body.appendChild(renderDashboard());
		} else if (view === 'pages') {
			body.appendChild(renderPages());
		} else if (view === 'blog') {
			body.appendChild(renderBlog());
		} else if (view === 'seo') {
			body.appendChild(renderSeo());
		} else if (view === 'media') {
			body.appendChild(renderMedia());
		} else if (view === 'backups') {
			body.appendChild(renderBackups());
		} else if (view === 'revisions') {
			body.appendChild(renderRevisions());
		} else if (view === 'health') {
			body.appendChild(renderHealth());
		} else if (VIEW_TO_DOC[view]) {
			body.appendChild(renderDocEditor(VIEW_TO_DOC[view]));
		} else {
			body.appendChild(el('p', { text: 'This screen does not exist yet.' }));
		}

		if (docNeedsSaveBar()) {
			main.appendChild(renderSaveBar());
		}
		updateSaveBar();
	}

	function renderSidebar() {
		var nav = el('nav', { class: 'tusb-sidebar', 'aria-label': 'Site Manager sections' });
		nav.appendChild(el('div', { class: 'tusb-sidebar__brand' }, [
			el('span', { class: 'tusb-sidebar__mark', 'aria-hidden': 'true', text: 'BRO' }),
			el('div', {}, [
				el('span', { class: 'tusb-sidebar__title', text: 'Site Manager' }),
				el('span', { class: 'tusb-sidebar__sub', text: 'TrustUsBro' })
			])
		]));
		NAV.forEach(function (group) {
			var section = el('div', { class: 'tusb-navgroup' }, [
				el('span', { class: 'tusb-navgroup__label', text: group.group })
			]);
			group.items.forEach(function (item) {
				var active = item.view === state.view;
				section.appendChild(el('a', {
					class: 'tusb-navitem' + (active ? ' is-active' : ''),
					href: T.pageUrl + '?page=tusb-' + item.view.replace(/_/g, '-'),
					'aria-current': active ? 'page' : null
				}, [
					el('span', { class: 'dashicons dashicons-' + item.icon, 'aria-hidden': 'true' }),
					el('span', { text: item.label }),
					pendingBadge(item.view)
				]));
			});
			nav.appendChild(section);
		});
		nav.appendChild(el('div', { class: 'tusb-sidebar__foot' }, [
			el('a', { class: 'tusb-link', href: T.siteUrl, target: '_blank', rel: 'noopener', text: 'View website ↗' })
		]));
		return nav;
	}

	function pendingBadge(view) {
		var docKey = VIEW_TO_DOC[view];
		if (!docKey || !state.boot || !state.boot.status || !state.boot.status[docKey] || !state.boot.status[docKey].has_unpublished) {
			return null;
		}
		return el('span', { class: 'tusb-badge', title: 'Unpublished changes', text: '●' });
	}

	function renderTopbar() {
		var bar = el('header', { class: 'tusb-topbar' });
		bar.appendChild(el('div', { class: 'tusb-topbar__titles' }, [
			el('h1', { class: 'tusb-topbar__title', text: titleForView() }),
			el('p', { class: 'tusb-topbar__sub', text: subtitleForView() })
		]));
		var actions = el('div', { class: 'tusb-topbar__actions' });
		if (state.doc && VIEW_TO_DOC[state.view] === state.doc) {
			actions.appendChild(el('a', {
				class: 'button',
				href: previewUrl(),
				target: '_blank',
				rel: 'noopener',
				text: '↗ ' + t('preview')
			}));
		}
		bar.appendChild(actions);
		return bar;
	}

	function titleForView() {
		var titles = {
			dashboard: 'Welcome back',
			pages: 'Homepage & pages',
			blog: 'Blog',
			seo: 'SEO',
			media: 'Media library',
			backups: 'Backups & recovery',
			revisions: 'Revision history',
			health: 'Health & help'
		};
		if (titles[state.view]) {
			return titles[state.view];
		}
		if (VIEW_TO_DOC[state.view]) {
			return labelOf(VIEW_TO_DOC[state.view]);
		}
		return 'Site Manager';
	}

	function subtitleForView() {
		var subs = {
			dashboard: 'Everything on your website, in plain language. Nothing goes live until you press Publish.',
			pages: 'Edit your homepage and about page: reorder sections, change text, add or remove anything.',
			blog: 'Write and schedule articles using native WordPress posts.',
			seo: 'Search titles, descriptions, sitemaps and structured data.',
			media: 'Images used across the site, with alt text and usage.',
			backups: 'Snapshots of your Site Manager content. Restore with one click.',
			revisions: 'Every saved version, with who changed what and when.',
			health: 'Compatibility, permissions and a quick self-test.'
		};
		if (subs[state.view]) {
			return subs[state.view];
		}
		if (state.view === 'header' || state.view === 'footer' || state.view === 'contact') {
			return 'These settings appear site-wide. Nothing goes live until you press Publish.';
		}
		return 'Add, edit, reorder and hide cards. Nothing goes live until you press Publish.';
	}

	function previewUrl() {
		var doc = currentDoc();
		return doc && doc.preview ? doc.preview : T.siteUrl;
	}

	function docNeedsSaveBar() {
		// Views that edit a document but are not a 1:1 document mapping.
		if (state.view === 'pages' || state.view === 'seo') {
			return true;
		}
		return Boolean(VIEW_TO_DOC[state.view]);
	}

	/* ------------------------------------------------------------------
	 * Save bar
	 * ------------------------------------------------------------------ */

	var saveBar = null;

	function renderSaveBar() {
		saveBar = el('div', { class: 'tusb-savebar', role: 'region', 'aria-label': 'Save and publish' }, [
			el('div', { class: 'tusb-savebar__status', id: 'tusb-save-status' }),
			el('div', { class: 'tusb-savebar__actions' }, [
				el('button', { class: 'button', type: 'button', id: 'tusb-discard', onclick: discardDoc, text: t('discard') }),
				el('button', { class: 'button', type: 'button', id: 'tusb-save', onclick: function () { saveDraft(); }, text: t('save') }),
				el('button', { class: 'button button-primary', type: 'button', id: 'tusb-publish', onclick: publishDoc, text: t('publish') })
			])
		]);
		return saveBar;
	}

	function updateSaveBar() {
		var status = document.getElementById('tusb-save-status');
		var saveBtn = document.getElementById('tusb-save');
		var publishBtn = document.getElementById('tusb-publish');
		if (!status) {
			return;
		}
		var doc = currentDoc();
		var text;
		var cls = 'tusb-savebar__status';
		if (state.saving) {
			text = t('saving');
			cls += ' is-busy';
		} else if (state.dirty) {
			text = 'Unsaved changes in this browser';
			cls += ' is-dirty';
		} else if (doc && doc.has_unpublished) {
			text = 'Draft saved. Not live yet — press Publish changes.';
			cls += ' is-dirty';
		} else if (doc && doc.meta && doc.meta.published_at) {
			text = 'All changes are live.';
			cls += ' is-clean';
		} else {
			text = 'No changes yet.';
		}
		status.className = cls;
		status.textContent = text;
		if (saveBtn) {
			saveBtn.disabled = state.saving || !state.dirty;
		}
		if (publishBtn) {
			publishBtn.disabled = state.saving || (!state.dirty && !(doc && doc.has_unpublished));
		}
	}

	/* ------------------------------------------------------------------
	 * Dashboard overview
	 * ------------------------------------------------------------------ */

	function renderDashboard() {
		var wrap = el('div', { class: 'tusb-stack' });

		var pending = [];
		var status = (state.boot && state.boot.status) || {};
		Object.keys(status).forEach(function (key) {
			if (status[key].has_unpublished) {
				pending.push(status[key]);
			}
		});

		if (pending.length) {
			wrap.appendChild(el('div', { class: 'tusb-callout tusb-callout--attention' }, [
				el('strong', { text: 'You have unpublished changes in ' + pending.length + ' area' + (pending.length > 1 ? 's' : '') + '.' }),
				el('span', { text: ' ' + pending.map(function (row) { return row.label; }).join(', ') + '.' }),
				el('a', { class: 'tusb-link', href: T.pageUrl + '?page=tusb-pages', text: 'Review and publish →' })
			]));
		}

		var grid = el('div', { class: 'tusb-cards' });
		var cards = [
			{ title: 'Homepage', desc: 'Reorder, hide, duplicate and edit every homepage section.', href: T.pageUrl + '?page=tusb-pages&doc=home', cta: 'Edit homepage' },
			{ title: 'Services & industries', desc: 'Add service or industry cards; they appear wherever those sections are used.', href: T.pageUrl + '?page=tusb-services', cta: 'Manage cards' },
			{ title: 'Case studies & testimonials', desc: 'Show real results and client quotes.', href: T.pageUrl + '?page=tusb-case-studies', cta: 'Manage case studies' },
			{ title: 'Header & footer', desc: 'Logo, menu, buttons and the four-column footer.', href: T.pageUrl + '?page=tusb-header', cta: 'Edit header' },
			{ title: 'Blog', desc: 'Write, schedule and categorise articles.', href: T.pageUrl + '?page=tusb-blog', cta: 'Open blog' },
			{ title: 'SEO', desc: 'Titles, descriptions, sitemap and schema.', href: T.pageUrl + '?page=tusb-seo', cta: 'Open SEO' },
			{ title: 'Backups', desc: 'Create or restore a snapshot before big changes.', href: T.pageUrl + '?page=tusb-backups', cta: 'Open backups' },
			{ title: 'Design settings', desc: 'Colours and fonts inherited from your theme.', href: T.pageUrl + '?page=tusb-design', cta: 'Open design' }
		];
		cards.forEach(function (card) {
			grid.appendChild(el('article', { class: 'tusb-card tusb-card--nav' }, [
				el('h2', { class: 'tusb-card__title', text: card.title }),
				el('p', { class: 'tusb-card__text', text: card.desc }),
				el('a', { class: 'tusb-link', href: card.href, text: card.cta + ' →' })
			]));
		});
		wrap.appendChild(grid);

		wrap.appendChild(el('div', { class: 'tusb-callout' }, [
			el('strong', { text: 'How this works: ' }),
			el('span', { text: 'changes are saved as a draft first. Your website visitors keep seeing the published version until you press Publish changes. Every publish creates a backup and a revision you can restore.' })
		]));

		return wrap;
	}

	/* ------------------------------------------------------------------
	 * Pages (sections editor with click-to-edit and drag-and-drop)
	 * ------------------------------------------------------------------ */

	function renderPages() {
		var wrap = el('div', { class: 'tusb-stack' });
		var docs = (state.boot && state.boot.defaults.page_docs) || { home: 'Homepage', about: 'About page' };
		var keys = Object.keys(docs);
		var active = state.doc && docs[state.doc] ? state.doc : keys[0];

		var tabs = el('div', { class: 'tusb-tabs', role: 'tablist' });
		keys.forEach(function (key) {
			tabs.appendChild(el('button', {
				class: 'tusb-tab' + (key === active ? ' is-active' : ''),
				type: 'button',
				role: 'tab',
				'aria-selected': key === active ? 'true' : 'false',
				onclick: function () {
					if (state.dirty && !window.confirm('You have unsaved changes on this screen. Discard them?')) {
						return;
					}
					state.doc = key;
					state.dirty = false;
					state.draft = null;
					state.draftDoc = '';
					state.selectedSection = null;
					loadDoc(key).then(function () {
						syncDraftFromServer();
						render();
					}).catch(function (error) { toast(error.message, 'error'); });
				}
			}, [docs[key]]));
		});
		wrap.appendChild(tabs);

		if (state.doc !== active) {
			state.doc = active;
		}

		if (!state.docs[active]) {
			wrap.appendChild(spinner('Loading ' + docs[active] + '…'));
			loadDoc(active).then(function () {
				syncDraftFromServer();
				render();
			}).catch(function (error) {
				wrap.appendChild(el('p', { class: 'tusb-error', text: error.message }));
			});
			return wrap;
		}

		if (!ensureDraft(active)) {
			return wrap;
		}

		var doc = state.docs[active];
		var sections = (state.draft && state.draft.sections) || [];

		wrap.appendChild(el('div', { class: 'tusb-toolbar' }, [
			el('span', { class: 'tusb-toolbar__hint', text: 'Drag the ⠿ handle to reorder, or use the arrow buttons. Click a heading or paragraph to edit it in place.' }),
			el('button', { class: 'button', type: 'button', onclick: function () { openAddSection(active); }, text: '+ Add section' })
		]));

		var list = el('ol', { class: 'tusb-sections', 'aria-label': 'Sections in order' });
		sections.forEach(function (section, index) {
			list.appendChild(renderSectionRow(section, index, active, doc));
		});
		wrap.appendChild(list);

		if (!sections.length) {
			wrap.appendChild(el('div', { class: 'tusb-empty-state' }, [
				el('p', { text: 'This page has no sections yet.' }),
				el('button', { class: 'button button-primary', type: 'button', onclick: function () { openAddSection(active); }, text: 'Add the first section' })
			]));
		}

		return wrap;
	}

	function sectionDef(docKey, type) {
		var doc = state.docs[docKey];
		if (!doc || !doc.schema || !doc.schema.sections) {
			return null;
		}
		return doc.schema.sections[type] || null;
	}

	function renderSectionRow(section, index, docKey, doc) {
		var def = sectionDef(docKey, section.type) || { label: section.type, fields: {} };
		var collapsed = state.collapsed[section.id];
		var row = el('li', {
			class: 'tusb-section-row' + (section.enabled ? '' : ' is-hidden') + (collapsed ? ' is-collapsed' : '') + (state.selectedSection === section.id ? ' is-selected' : ''),
			draggable: 'true',
			dataset: { id: section.id, index: String(index) }
		});

		row.addEventListener('dragstart', function (event) {
			event.dataTransfer.setData('text/plain', String(index));
			event.dataTransfer.effectAllowed = 'move';
			row.classList.add('is-dragging');
		});
		row.addEventListener('dragend', function () { row.classList.remove('is-dragging'); });
		row.addEventListener('dragover', function (event) {
			event.preventDefault();
			event.dataTransfer.dropEffect = 'move';
			row.classList.add('is-drop-target');
		});
		row.addEventListener('dragleave', function () { row.classList.remove('is-drop-target'); });
		row.addEventListener('drop', function (event) {
			event.preventDefault();
			row.classList.remove('is-drop-target');
			var from = parseInt(event.dataTransfer.getData('text/plain'), 10);
			if (isNaN(from) || from === index) {
				return;
			}
			moveSection(from, index);
		});

		var head = el('div', { class: 'tusb-section-row__head' }, [
			el('span', { class: 'tusb-drag', 'aria-hidden': 'true', title: 'Drag to reorder', text: '⠿' }),
			el('button', {
				class: 'tusb-section-row__title',
				type: 'button',
				'aria-expanded': collapsed ? 'false' : 'true',
				onclick: function () {
					state.collapsed[section.id] = !state.collapsed[section.id];
					render();
				}
			}, [
				el('span', { class: 'tusb-section-row__label', text: def.label || section.type }),
				el('span', { class: 'tusb-section-row__meta', text: sectionMeta(section) })
			]),
			el('div', { class: 'tusb-section-row__tools' }, [
				el('button', {
					class: 'tusb-iconbtn',
					type: 'button',
					title: section.enabled ? 'Hide this section' : 'Show this section',
					'aria-pressed': section.enabled ? 'true' : 'false',
					text: section.enabled ? '◉' : '○',
					onclick: function () {
						section.enabled = !section.enabled;
						markDirty();
						render();
					}
				}),
				el('button', { class: 'tusb-iconbtn', type: 'button', title: t('moveUp'), 'aria-label': 'Move ' + (def.label || section.type) + ' up', text: '↑', onclick: function () { moveSection(index, index - 1); } }),
				el('button', { class: 'tusb-iconbtn', type: 'button', title: t('moveDown'), 'aria-label': 'Move ' + (def.label || section.type) + ' down', text: '↓', onclick: function () { moveSection(index, index + 1); } }),
				el('button', { class: 'tusb-iconbtn', type: 'button', title: t('duplicate'), 'aria-label': 'Duplicate ' + (def.label || section.type), text: '⧉', onclick: function () { duplicateSection(index); } }),
				el('button', { class: 'tusb-iconbtn tusb-iconbtn--danger', type: 'button', title: 'Remove section', 'aria-label': 'Remove ' + (def.label || section.type), text: '✕', onclick: function () { removeSection(index); } })
			])
		]);
		row.appendChild(head);

		if (!collapsed) {
			var body = el('div', { class: 'tusb-section-row__body' });
			body.appendChild(renderFields(def.fields || {}, section, '', section.type, docKey));
			if (def.description) {
				body.appendChild(el('p', { class: 'tusb-help', text: def.description }));
			}
			var foot = el('div', { class: 'tusb-section-row__foot' });
			if (def.source) {
				foot.appendChild(el('a', {
					class: 'tusb-link',
					href: T.pageUrl + '?page=tusb-' + def.source.replace(/_/g, '-'),
					text: 'Edit the ' + labelOf(def.source) + ' cards →'
				}));
			}
			foot.appendChild(el('a', {
				class: 'tusb-link',
				href: (doc.preview || previewUrl()) + '#tusb-' + encodeURIComponent(section.id),
				target: '_blank',
				rel: 'noopener',
				text: 'Open preview of this page ↗'
			}));
			body.appendChild(foot);
			row.appendChild(body);
		}

		return row;
	}

	function sectionMeta(section) {
		var parts = [];
		if (!section.enabled) {
			parts.push('hidden');
		}
		['heading', 'title'].forEach(function (key) {
			if (section[key] && typeof section[key] === 'string') {
				parts.push(section[key].length > 48 ? section[key].slice(0, 48) + '…' : section[key]);
			}
		});
		['steps', 'principles', 'buttons'].forEach(function (key) {
			if (section[key] && section[key].length) {
				parts.push(section[key].length + ' ' + key);
			}
		});
		return parts.join(' · ');
	}

	function moveSection(from, to) {
		var sections = state.draft.sections;
		if (to < 0 || to >= sections.length || from === to) {
			return;
		}
		var moved = sections.splice(from, 1)[0];
		sections.splice(to, 0, moved);
		markDirty();
		render();
		toast('Section moved. Remember to publish.', 'info');
	}

	function duplicateSection(index) {
		var sections = state.draft.sections;
		var copy = clone(sections[index]);
		copy.id = copy.type.replace(/-/g, '_') + '-' + Math.random().toString(36).slice(2, 8);
		copy.enabled = false;
		regenIds(copy);
		sections.splice(index + 1, 0, copy);
		markDirty();
		render();
		toast('Section duplicated (hidden until you show it).', 'info');
	}

	function regenIds(node) {
		if (Array.isArray(node)) {
			node.forEach(regenIds);
			return;
		}
		if (node && typeof node === 'object') {
			if (node.id && typeof node.id === 'string') {
				node.id = node.id.replace(/-[a-z0-9]{6}$/, '') + '-' + Math.random().toString(36).slice(2, 8);
			}
			Object.keys(node).forEach(function (key) {
				if (key !== 'id') {
					regenIds(node[key]);
				}
			});
		}
	}

	function removeSection(index) {
		if (!window.confirm(t('confirmDeleteSection'))) {
			return;
		}
		var sections = state.draft.sections;
		var removed = sections.splice(index, 1)[0];
		var at = index;
		markDirty();
		render();
		toast('Section removed.', 'info', {
			label: t('undo'),
			run: function () {
				state.draft.sections.splice(at, 0, removed);
				markDirty();
				render();
			}
		});
	}

	function openAddSection(docKey) {
		var doc = state.docs[docKey];
		var defs = doc && doc.schema && doc.schema.sections ? doc.schema.sections : {};
		var existing = (state.draft.sections || []).map(function (section) { return section.type; });

		var overlay = el('div', { class: 'tusb-modal', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'tusb-add-title' });
		var box = el('div', { class: 'tusb-modal__box' });
		box.appendChild(el('h2', { class: 'tusb-modal__title', id: 'tusb-add-title', text: 'Add a section' }));
		box.appendChild(el('p', { class: 'tusb-help', text: 'Sections inherit your theme design automatically. New sections are added at the end of the page and stay hidden until you show them.' }));

		var list = el('div', { class: 'tusb-addlist' });
		Object.keys(defs).forEach(function (type) {
			var def = defs[type];
			list.appendChild(el('button', {
				class: 'tusb-addlist__item',
				type: 'button',
				onclick: function () {
					addSection(docKey, type);
					close();
				}
			}, [
				el('span', { class: 'tusb-addlist__label', text: def.label || type }),
				el('span', { class: 'tusb-addlist__desc', text: def.description || '' }),
				existing.indexOf(type) > -1 ? el('span', { class: 'tusb-addlist__tag', text: 'already on page' }) : null
			]));
		});
		box.appendChild(list);
		box.appendChild(el('div', { class: 'tusb-modal__actions' }, [
			el('button', { class: 'button', type: 'button', text: 'Cancel', onclick: close })
		]));

		function close() {
			overlay.parentNode && overlay.parentNode.removeChild(overlay);
		}

		overlay.appendChild(box);
		overlay.addEventListener('click', function (event) {
			if (event.target === overlay) {
				close();
			}
		});
		document.addEventListener('keydown', function onEsc(event) {
			if (event.key === 'Escape') {
				close();
				document.removeEventListener('keydown', onEsc);
			}
		});
		document.body.appendChild(overlay);
		box.querySelector('button').focus();
	}

	function addSection(docKey, type) {
		var doc = state.docs[docKey];
		var def = doc.schema.sections[type];
		var section = { id: type.replace(/-/g, '_') + '-' + Math.random().toString(36).slice(2, 8), type: type, enabled: false };
		Object.keys(def.fields || {}).forEach(function (key) {
			section[key] = defaultForField(def.fields[key]);
		});
		state.draft.sections.push(section);
		markDirty();
		render();
		toast('Section added (hidden). Press the ◉ button to show it.', 'info');
	}

	function defaultForField(field) {
		if (field.default !== undefined) {
			return clone(field.default);
		}
		switch (field.type) {
			case 'repeater': return [];
			case 'group':
				var group = {};
				Object.keys(field.fields || {}).forEach(function (key) {
					group[key] = defaultForField(field.fields[key]);
				});
				return group;
			case 'toggle': return false;
			case 'number': return 0;
			case 'image': return 0;
			default: return '';
		}
	}

	/* ------------------------------------------------------------------
	 * Field rendering (shared by all editors)
	 * ------------------------------------------------------------------ */

	function renderFields(fields, values, prefix, contextLabel) {
		var wrap = el('div', { class: 'tusb-fields' });
		Object.keys(fields).forEach(function (key) {
			var field = fields[key];
			var path = prefix ? prefix + '.' + key : key;
			var value = values && values[key] !== undefined ? values[key] : defaultForField(field);
			wrap.appendChild(renderField(field, value, path, key, values, contextLabel));
		});
		return wrap;
	}

	function renderField(field, value, path, key, parent, contextLabel) {
		var id = 'tusb-f-' + path.replace(/[^a-z0-9]/gi, '-').toLowerCase();
		var label = field.label || key.replace(/_/g, ' ');
		var wrap = el('div', { class: 'tusb-field tusb-field--' + (field.type || 'text') });

		if (field.type === 'toggle') {
			var checkbox = el('input', { type: 'checkbox', id: id, checked: Boolean(value) });
			checkbox.addEventListener('change', function () {
				parent[key] = checkbox.checked;
				markDirty();
			});
			wrap.appendChild(el('label', { class: 'tusb-toggle', for: id }, [checkbox, el('span', { text: label })]));
			if (field.help) {
				wrap.appendChild(el('p', { class: 'tusb-help', text: field.help }));
			}
			return wrap;
		}

		wrap.appendChild(el('label', { class: 'tusb-field__label', for: id, text: label }));

		var input;
		if (field.type === 'textarea' || field.type === 'html') {
			input = el('textarea', { id: id, rows: field.type === 'html' ? 6 : 3 });
			input.value = value || '';
			input.addEventListener('input', debounce(function () {
				parent[key] = input.value;
				markDirty();
			}, 150));
		} else if (field.type === 'select') {
			input = el('select', { id: id });
			Object.keys(field.options || {}).forEach(function (optionValue) {
				var option = el('option', { value: optionValue, text: field.options[optionValue] });
				if (String(optionValue) === String(value)) {
					option.selected = true;
				}
				input.appendChild(option);
			});
			input.addEventListener('change', function () {
				parent[key] = input.value;
				markDirty();
			});
		} else if (field.type === 'number') {
			input = el('input', { type: 'number', id: id, min: field.min, max: field.max, value: value });
			input.addEventListener('input', function () {
				parent[key] = parseInt(input.value, 10) || 0;
				markDirty();
			});
		} else if (field.type === 'image') {
			return renderImageField(field, value, parent, key, id, label, wrap);
		} else if (field.type === 'color') {
			var colorWrap = el('div', { class: 'tusb-colorfield' });
			var color = el('input', { type: 'color', id: id, 'aria-label': label, value: /^#[0-9a-f]{6}$/i.test(value || '') ? value : '#000000' });
			var text = el('input', { type: 'text', value: value || '', placeholder: 'Inherit from theme' });
			color.addEventListener('input', function () {
				parent[key] = color.value;
				text.value = color.value;
				markDirty();
			});
			text.addEventListener('input', function () {
				parent[key] = text.value;
				markDirty();
			});
			colorWrap.appendChild(color);
			colorWrap.appendChild(text);
			if (field.help) {
				wrap.appendChild(el('p', { class: 'tusb-help', text: field.help }));
			}
			wrap.appendChild(colorWrap);
			return wrap;
		} else if (field.type === 'repeater') {
			wrap.appendChild(renderRepeater(field, value || [], path, label, parent, key));
			if (field.help) {
				wrap.appendChild(el('p', { class: 'tusb-help', text: field.help }));
			}
			return wrap;
		} else if (field.type === 'group') {
			wrap.appendChild(renderFields(field.fields || {}, value || {}, path, label));
			return wrap;
		} else {
			var inputType = field.type === 'url' ? 'url' : (field.type === 'email' ? 'email' : (field.type === 'tel' ? 'tel' : 'text'));
			input = el('input', { type: inputType, id: id, value: value || '' });
			input.addEventListener('input', debounce(function () {
				parent[key] = input.value;
				markDirty();
			}, 150));
		}

		wrap.appendChild(input);
		if (field.help) {
			wrap.appendChild(el('p', { class: 'tusb-help', text: field.help }));
		}
		if (field.required) {
			wrap.classList.add('is-required');
		}
		return wrap;
	}

	function renderImageField(field, value, parent, key, id, label, wrap) {
		var current = el('div', { class: 'tusb-imagefield__preview' });
		var buttons = el('div', { class: 'tusb-imagefield__actions' });

		function paint(imageId, url, title) {
			current.innerHTML = '';
			if (imageId && url) {
				current.appendChild(el('img', { src: url, alt: '' }));
				current.appendChild(el('span', { class: 'tusb-imagefield__name', text: title || ('Image #' + imageId) }));
			} else {
				current.appendChild(el('span', { class: 'tusb-imagefield__empty', text: 'No image — the theme default is used.' }));
			}
		}

		function choose() {
			if (!window.wp || !window.wp.media) {
				toast('The WordPress media library did not load. Reload the page and try again.', 'error');
				return;
			}
			var frame = window.wp.media({
				title: (T.media && T.media.libraryTitle) || 'Choose an image',
				button: { text: (T.media && T.media.libraryButton) || 'Use this image' },
				library: { type: 'image' },
				multiple: false
			});
			frame.on('select', function () {
				var attachment = frame.state().get('selection').first().toJSON();
				parent[key] = attachment.id;
				paint(attachment.id, attachment.sizes && attachment.sizes.medium ? attachment.sizes.medium.url : attachment.url, attachment.title);
				markDirty();
			});
			frame.open();
		}

		buttons.appendChild(el('button', { class: 'button', type: 'button', text: 'Choose image', onclick: choose }));
		buttons.appendChild(el('button', {
			class: 'button-link',
			type: 'button',
			text: 'Remove',
			onclick: function () {
				parent[key] = 0;
				paint(0);
				markDirty();
			},
			style: 'margin-left:10px'
		}));

		wrap.appendChild(el('label', { class: 'tusb-field__label', for: id, text: label }));
		wrap.appendChild(current);
		wrap.appendChild(buttons);
		if (field.help) {
			wrap.appendChild(el('p', { class: 'tusb-help', text: field.help }));
		}

		if (value) {
			paint(value);
			// Resolve the attachment URL without an extra endpoint round trip.
			if (window.wp && window.wp.media) {
				window.wp.media.attachment(value).fetch().then(function () {
					var data = window.wp.media.attachment(value).toJSON();
					if (data && (data.url || data.sizes)) {
						paint(value, data.sizes && data.sizes.medium ? data.sizes.medium.url : data.url, data.title);
					}
				});
			}
		}
		return wrap;
	}

	function renderRepeater(field, rows, path, label, parent, key) {
		var wrap = el('div', { class: 'tusb-repeater' });
		var max = field.max || 50;

		function repaint() {
			wrap.innerHTML = '';
			rows.forEach(function (row, index) {
				var card = el('div', {
					class: 'tusb-repeater__row',
					draggable: 'true',
					dataset: { index: String(index) }
				});
				card.addEventListener('dragstart', function (event) {
					event.dataTransfer.setData('text/plain', 'repeater:' + index);
				});
				card.addEventListener('dragover', function (event) {
					event.preventDefault();
					card.classList.add('is-drop-target');
				});
				card.addEventListener('dragleave', function () { card.classList.remove('is-drop-target'); });
				card.addEventListener('drop', function (event) {
					event.preventDefault();
					card.classList.remove('is-drop-target');
					var payload = event.dataTransfer.getData('text/plain');
					if (payload.indexOf('repeater:') !== 0) {
						return;
					}
					var from = parseInt(payload.split(':')[1], 10);
					if (isNaN(from) || from === index) {
						return;
					}
					var moved = rows.splice(from, 1)[0];
					rows.splice(index, 0, moved);
					parent[key] = rows;
					markDirty();
					repaint();
				});

				var head = el('div', { class: 'tusb-repeater__head' }, [
					el('span', { class: 'tusb-drag', 'aria-hidden': 'true', text: '⠿' }),
					el('span', { class: 'tusb-repeater__index', text: rowTitle(field, row, index) }),
					el('div', { class: 'tusb-repeater__tools' }, [
						el('button', { class: 'tusb-iconbtn', type: 'button', text: '↑', title: t('moveUp'), 'aria-label': 'Move item up', onclick: function () { if (index > 0) { rows.splice(index - 1, 0, rows.splice(index, 1)[0]); markDirty(); repaint(); } } }),
						el('button', { class: 'tusb-iconbtn', type: 'button', text: '↓', title: t('moveDown'), 'aria-label': 'Move item down', onclick: function () { if (index < rows.length - 1) { rows.splice(index + 1, 0, rows.splice(index, 1)[0]); markDirty(); repaint(); } } }),
						el('button', { class: 'tusb-iconbtn', type: 'button', text: '⧉', title: t('duplicate'), 'aria-label': 'Duplicate item', onclick: function () { var copy = clone(row); regenIds(copy); rows.splice(index + 1, 0, copy); markDirty(); repaint(); } }),
						el('button', { class: 'tusb-iconbtn tusb-iconbtn--danger', type: 'button', text: '✕', title: t('remove'), 'aria-label': 'Remove item', onclick: function () { if (window.confirm(t('confirmDeleteItem'))) { rows.splice(index, 1); markDirty(); repaint(); } } })
					])
				]);
				card.appendChild(head);
				card.appendChild(renderFields(field.fields || {}, row, path + '.' + index, label));
				wrap.appendChild(card);
			});

			if (rows.length < max) {
				wrap.appendChild(el('button', {
					class: 'button tusb-repeater__add',
					type: 'button',
					text: '+ Add ' + label.toLowerCase().replace(/s$/, ''),
					onclick: function () {
						var row = {};
						Object.keys(field.fields || {}).forEach(function (fieldKey) {
							row[fieldKey] = defaultForField(field.fields[fieldKey]);
						});
						row.id = Math.random().toString(36).slice(2, 9);
						rows.push(row);
						parent[key] = rows;
						markDirty();
						repaint();
					}
				}));
			}
		}

		repaint();
		return wrap;
	}

	function rowTitle(field, row, index) {
		var candidates = ['label', 'title', 'name', 'question', 'quote', 'text', 'url'];
		for (var i = 0; i < candidates.length; i++) {
			var value = row[candidates[i]];
			if (typeof value === 'string' && value.trim()) {
				return value.length > 60 ? value.slice(0, 60) + '…' : value;
			}
		}
		return 'Item ' + (index + 1);
	}

	function debounce(fn, wait) {
		var timer;
		return function () {
			var args = arguments;
			var context = this;
			window.clearTimeout(timer);
			timer = window.setTimeout(function () {
				fn.apply(context, args);
			}, wait);
		};
	}

	/* ------------------------------------------------------------------
	 * Collection editors (services, industries, case studies, …)
	 * ------------------------------------------------------------------ */

	function renderDocEditor(docKey) {
		var wrap = el('div', { class: 'tusb-stack' });
		state.doc = docKey;

		if (!state.docs[docKey]) {
			wrap.appendChild(spinner('Loading ' + labelOf(docKey) + '…'));
			loadDoc(docKey).then(function () {
				syncDraftFromServer();
				render();
			}).catch(function (error) {
				wrap.appendChild(el('p', { class: 'tusb-error', text: error.message }));
			});
			return wrap;
		}
		if (!ensureDraft(docKey)) {
			return wrap;
		}

		var doc = state.docs[docKey];
		var type = doc.schema.type;

		if (type === 'collection') {
			wrap.appendChild(renderCollection(docKey, doc));
		} else if (type === 'sections') {
			// Pages reached from the "pages" view.
			var tabs = el('div', { class: 'tusb-tabs' });
			wrap.appendChild(tabs);
			wrap.appendChild(renderSectionListForDoc(docKey, doc));
		} else {
			wrap.appendChild(renderRecord(docKey, doc));
		}
		return wrap;
	}

	function renderSectionListForDoc(docKey, doc) {
		var wrap = el('div', {});
		wrap.appendChild(el('div', { class: 'tusb-toolbar' }, [
			el('span', { class: 'tusb-toolbar__hint', text: 'Drag to reorder. Click a section title to expand it.' }),
			el('button', { class: 'button', type: 'button', onclick: function () { openAddSection(docKey); }, text: '+ Add section' })
		]));
		var list = el('ol', { class: 'tusb-sections' });
		(state.draft.sections || []).forEach(function (section, index) {
			list.appendChild(renderSectionRow(section, index, docKey, doc));
		});
		wrap.appendChild(list);
		return wrap;
	}

	function renderCollection(docKey, doc) {
		var wrap = el('div', { class: 'tusb-stack' });
		var items = state.draft.items || (state.draft.items = []);
		var fields = doc.schema.item_fields || {};

		wrap.appendChild(el('div', { class: 'tusb-toolbar' }, [
			el('span', { class: 'tusb-toolbar__hint', text: items.length + ' item' + (items.length === 1 ? '' : 's') + ' · drag ⠿ to reorder' }),
			el('button', {
				class: 'button button-primary',
				type: 'button',
				text: '+ Add ' + (doc.schema.item_label || 'item'),
				onclick: function () {
					var item = { id: Math.random().toString(36).slice(2, 9), visible: true };
					Object.keys(fields).forEach(function (key) {
						item[key] = defaultForField(fields[key]);
					});
					items.push(item);
					markDirty();
					render();
				}
			})
		]));

		if (!items.length) {
			var empty = el('div', { class: 'tusb-empty-state' }, [
				el('p', { text: 'Nothing here yet. This section stays hidden on the website until you add the first item.' }),
				el('button', { class: 'button', type: 'button', text: 'Load example content', onclick: loadDemo })
			]);
			wrap.appendChild(empty);
		}

		items.forEach(function (item, index) {
			var card = el('div', {
				class: 'tusb-collection-row' + (item.visible === false ? ' is-hidden' : ''),
				draggable: 'true'
			});
			card.addEventListener('dragstart', function (event) {
				event.dataTransfer.setData('text/plain', String(index));
			});
			card.addEventListener('dragover', function (event) { event.preventDefault(); card.classList.add('is-drop-target'); });
			card.addEventListener('dragleave', function () { card.classList.remove('is-drop-target'); });
			card.addEventListener('drop', function (event) {
				event.preventDefault();
				card.classList.remove('is-drop-target');
				var from = parseInt(event.dataTransfer.getData('text/plain'), 10);
				if (isNaN(from) || from === index) {
					return;
				}
				items.splice(index, 0, items.splice(from, 1)[0]);
				markDirty();
				render();
			});

			card.appendChild(el('div', { class: 'tusb-collection-row__head' }, [
				el('span', { class: 'tusb-drag', 'aria-hidden': 'true', text: '⠿' }),
				el('span', { class: 'tusb-collection-row__title', text: item.title || item.question || item.name || item.quote || ('Item ' + (index + 1)) }),
				el('div', { class: 'tusb-collection-row__tools' }, [
					el('button', {
						class: 'tusb-iconbtn',
						type: 'button',
						title: item.visible === false ? 'Show on website' : 'Hide from website',
						text: item.visible === false ? '○' : '◉',
						onclick: function () {
							item.visible = item.visible === false;
							markDirty();
							render();
						}
					}),
					el('button', { class: 'tusb-iconbtn', type: 'button', text: '↑', 'aria-label': 'Move up', onclick: function () { if (index > 0) { items.splice(index - 1, 0, items.splice(index, 1)[0]); markDirty(); render(); } } }),
					el('button', { class: 'tusb-iconbtn', type: 'button', text: '↓', 'aria-label': 'Move down', onclick: function () { if (index < items.length - 1) { items.splice(index + 1, 0, items.splice(index, 1)[0]); markDirty(); render(); } } }),
					el('button', {
						class: 'tusb-iconbtn',
						type: 'button',
						text: '⧉',
						'aria-label': 'Duplicate',
						onclick: function () {
							var copy = clone(item);
							regenIds(copy);
							items.splice(index + 1, 0, copy);
							markDirty();
							render();
						}
					}),
					el('button', {
						class: 'tusb-iconbtn tusb-iconbtn--danger',
						type: 'button',
						text: '✕',
						'aria-label': 'Delete',
						onclick: function () {
							if (!window.confirm('Delete \u201c' + (item.title || item.question || 'this item') + '\u201d?')) {
								return;
							}
							var removed = items.splice(index, 1)[0];
							markDirty();
							render();
							toast('Item deleted from the draft. Publish to remove it from your live site.', 'info', {
								label: t('undo'),
								run: function () {
									items.splice(index, 0, removed);
									markDirty();
									render();
								}
							});
						}
					})
			])
		]));
			card.appendChild(renderFields(fields, item, '', docKey));
			wrap.appendChild(card);
		});

		return wrap;
	}

	function renderRecord(docKey, doc) {
		var values = state.draft || {};
		var wrap = el('div', { class: 'tusb-stack' });
		if (doc.schema.description) {
			wrap.appendChild(el('p', { class: 'tusb-help', text: doc.schema.description }));
		}
		wrap.appendChild(renderFields(doc.schema.fields || {}, values, '', docKey));
		if (docKey === 'design') {
			wrap.appendChild(renderDesignExtras());
		}
		return wrap;
	}

	function renderDesignExtras() {
		var box = el('div', { class: 'tusb-callout' });
		box.appendChild(el('strong', { text: 'Design safety: ' }));
		box.appendChild(el('span', { text: 'These tokens only override values you set. Everything left empty inherits your active theme, so the approved TrustUsBro design is preserved. Changing colours here is optional.' }));
		return box;
	}

	function loadDemo() {
		api('demo', { method: 'POST' }).then(function (result) {
			toast(result.message, 'success');
			Object.keys(state.docs).forEach(function (key) { delete state.docs[key]; });
			render();
		}).catch(function (error) {
			toast(error.message, 'error');
		});
	}
	/* ------------------------------------------------------------------
	 * Blog manager
	 * ------------------------------------------------------------------ */

	var blogState = { data: null, editing: null, filter: { status: 'all', page: 1 } };

	function renderBlog() {
		var wrap = el('div', { class: 'tusb-stack' });

		if (!blogState.data) {
			wrap.appendChild(spinner('Loading articles…'));
			api('blog?status=' + encodeURIComponent(blogState.filter.status) + '&page=' + blogState.filter.page).then(function (data) {
				blogState.data = data;
				render();
			}).catch(function (error) {
				wrap.appendChild(el('p', { class: 'tusb-error', text: error.message }));
			});
			return wrap;
		}

		var data = blogState.data;

		wrap.appendChild(el('div', { class: 'tusb-toolbar' }, [
			el('div', { class: 'tusb-filters' }, [
				selectFilter('Status', 'status', { all: 'All', publish: 'Published', draft: 'Drafts', future: 'Scheduled', pending: 'Pending' }, blogState.filter.status, function (value) {
					blogState.filter.status = value;
					blogState.filter.page = 1;
					refreshBlog();
				})
			]),
			el('div', {}, [
				el('a', { class: 'button', href: T.links.new_post, text: 'Open block editor' }),
				el('button', {
					class: 'button button-primary',
					type: 'button',
					style: 'margin-left:8px',
					text: '+ New article',
					onclick: function () { openPostEditor(null); }
				})
			])
		]));

		var table = el('table', { class: 'tusb-table' });
		table.appendChild(el('thead', {}, [
			el('tr', {}, [
				el('th', { scope: 'col', text: 'Article' }),
				el('th', { scope: 'col', text: 'Status' }),
				el('th', { scope: 'col', text: 'Categories' }),
				el('th', { scope: 'col', text: 'SEO' }),
				el('th', { scope: 'col', text: 'Actions' })
			])
		]));
		var body = el('tbody');
		if (!data.items.length) {
			body.appendChild(el('tr', {}, [el('td', { colspan: '5' }, [el('p', { class: 'tusb-help', text: 'No articles yet. Create your first one — it uses native WordPress posts, so your URLs and feeds keep working.' })])]));
		}
		data.items.forEach(function (post) {
			body.appendChild(el('tr', {}, [
				el('td', {}, [
					el('strong', { text: post.title || '(no title)' }),
					el('div', { class: 'tusb-help', text: post.date_label + ' · ' + post.author })
				]),
				el('td', {}, [el('span', { class: 'tusb-pill tusb-pill--' + post.status, text: post.status_label })]),
				el('td', { text: post.categories.map(function (category) { return category.name; }).join(', ') || '—' }),
				el('td', {}, [
					el('span', { class: 'tusb-pill ' + (post.seo_title && post.seo_desc ? 'tusb-pill--publish' : 'tusb-pill--draft'), text: post.seo_title && post.seo_desc ? 'Set' : 'Missing' })
				]),
				el('td', { class: 'tusb-table__actions' }, [
					el('button', { class: 'button button-small', type: 'button', text: 'Edit', onclick: function () { openPostEditor(post); } }),
					el('a', { class: 'button button-small', href: post.view_link, target: '_blank', rel: 'noopener', text: 'View' }),
					el('a', { class: 'button-link', href: post.edit_link, text: 'Block editor' })
				])
			]));
		});
		table.appendChild(body);
		wrap.appendChild(table);

		if (data.pages > 1) {
			var pager = el('div', { class: 'tusb-pager' });
			for (var page = 1; page <= data.pages; page++) {
				(function (pageNumber) {
					pager.appendChild(el('button', {
						class: 'button' + (pageNumber === data.page ? ' button-primary' : ''),
						type: 'button',
						text: String(pageNumber),
						onclick: function () {
							blogState.filter.page = pageNumber;
							refreshBlog();
						}
					}));
				})(page);
			}
			wrap.appendChild(pager);
		}

		wrap.appendChild(renderCategoryManager(data.categories));

		if (blogState.editing) {
			wrap.appendChild(renderPostEditor());
		}
		return wrap;
	}

	function refreshBlog() {
		blogState.data = null;
		render();
	}

	function selectFilter(label, key, options, current, onChange) {
		var select = el('select', { 'aria-label': label });
		Object.keys(options).forEach(function (value) {
			var option = el('option', { value: value, text: options[value] });
			if (value === current) {
				option.selected = true;
			}
			select.appendChild(option);
		});
		select.addEventListener('change', function () { onChange(select.value); });
		return select;
	}

	function renderCategoryManager(categories) {
		var box = el('details', { class: 'tusb-panel' });
		box.appendChild(el('summary', { text: 'Categories (' + categories.length + ')' }));
		var list = el('ul', { class: 'tusb-plainlist' });
		categories.forEach(function (category) {
			list.appendChild(el('li', {}, [
				el('strong', { text: category.name }),
				el('span', { class: 'tusb-help', text: ' · ' + category.count + ' article' + (category.count === 1 ? '' : 's') }),
				el('button', {
					class: 'button-link',
					type: 'button',
					style: 'margin-left:10px;color:#b32d2e',
					text: 'Delete',
					onclick: function () {
						if (!window.confirm('Delete the category “' + category.name + '”? Articles are kept and moved to Uncategorised.')) {
							return;
						}
						api('blog/category', { method: 'DELETE', body: { id: category.id } }).then(function (result) {
							blogState.data.categories = result.data;
							render();
						}).catch(function (error) { toast(error.message, 'error'); });
					}
				})
			]));
		});
		box.appendChild(list);

		var name = el('input', { type: 'text', placeholder: 'New category name' });
		box.appendChild(el('div', { class: 'tusb-inline-form' }, [
			name,
			el('button', {
				class: 'button',
				type: 'button',
				text: 'Add category',
				onclick: function () {
					if (!name.value.trim()) {
						return;
					}
					api('blog/category', { method: 'POST', body: { category: { name: name.value } } }).then(function (result) {
						blogState.data.categories = result.data;
						render();
					}).catch(function (error) { toast(error.message, 'error'); });
				}
			})
		]));
		return box;
	}

	function openPostEditor(post) {
		blogState.editing = post ? clone(post) : { id: 0, title: '', excerpt: '', status: 'draft', categories: [], seo_title: '', seo_desc: '', thumbnail: 0, content: '' };
		render();
	}

	function renderPostEditor() {
		var post = blogState.editing;
		var data = blogState.data;
		var box = el('div', { class: 'tusb-panel tusb-panel--editor' });
		box.appendChild(el('h2', { class: 'tusb-panel__title', text: post.id ? 'Edit article' : 'New article' }));

		var fields = el('div', { class: 'tusb-fields' });

		var title = el('input', { type: 'text', value: post.title });
		fields.appendChild(el('div', { class: 'tusb-field' }, [el('label', { class: 'tusb-field__label', text: 'Title' }), title]));

		var excerpt = el('textarea', { rows: 3 });
		excerpt.value = post.excerpt || '';
		fields.appendChild(el('div', { class: 'tusb-field' }, [
			el('label', { class: 'tusb-field__label', text: 'Summary (used in listings and search results)' }),
			excerpt
		]));

		var status = el('select', {});
		[['draft', 'Draft'], ['publish', 'Published'], ['future', 'Scheduled'], ['private', 'Private']].forEach(function (option) {
			var node = el('option', { value: option[0], text: option[1] });
			if (option[0] === post.status) {
				node.selected = true;
			}
			status.appendChild(node);
		});
		fields.appendChild(el('div', { class: 'tusb-field' }, [el('label', { class: 'tusb-field__label', text: 'Status' }), status]));

		var date = el('input', { type: 'datetime-local', value: post.date ? post.date.slice(0, 16) : '' });
		fields.appendChild(el('div', { class: 'tusb-field' }, [
			el('label', { class: 'tusb-field__label', text: 'Publish date (used for scheduling)' }),
			date
		]));

		var categoryWrap = el('div', { class: 'tusb-checkboxes' });
		(data.categories || []).forEach(function (category) {
			var checkbox = el('input', { type: 'checkbox', value: String(category.id) });
			if ((post.categories || []).some(function (existing) { return existing.id === category.id; })) {
				checkbox.checked = true;
			}
			categoryWrap.appendChild(el('label', {}, [checkbox, el('span', { text: category.name })]));
		});
		fields.appendChild(el('div', { class: 'tusb-field' }, [el('span', { class: 'tusb-field__label', text: 'Categories' }), categoryWrap]));

		var seoTitle = el('input', { type: 'text', value: post.seo_title || '', maxlength: '70' });
		var seoDesc = el('textarea', { rows: 2, maxlength: '180' });
		seoDesc.value = post.seo_desc || '';
		fields.appendChild(el('div', { class: 'tusb-field' }, [el('label', { class: 'tusb-field__label', text: 'SEO title (optional)' }), seoTitle]));
		fields.appendChild(el('div', { class: 'tusb-field' }, [el('label', { class: 'tusb-field__label', text: 'Meta description (optional)' }), seoDesc]));

		fields.appendChild(el('p', { class: 'tusb-help', text: 'Article body is edited in the native block editor, so you get every Gutenberg block and don’t lose features. Save this panel first, then use “Body & blocks”.' }));

		box.appendChild(fields);

		box.appendChild(el('div', { class: 'tusb-panel__actions' }, [
			el('button', { class: 'button', type: 'button', text: 'Cancel', onclick: function () { blogState.editing = null; render(); } }),
			el('button', {
				class: 'button',
				type: 'button',
				text: 'Save',
				onclick: function () { savePost(false); }
			}),
			el('button', {
				class: 'button button-primary',
				type: 'button',
				text: 'Save & close',
				onclick: function () { savePost(true); }
			}),
			post.id ? el('a', { class: 'button', href: post.edit_link, text: 'Body & blocks' }) : null
		]));

		function savePost(close) {
			var payload = {
				id: post.id || 0,
				title: title.value,
				excerpt: excerpt.value,
				status: status.value,
				date: date.value || '',
				seo_title: seoTitle.value,
				seo_desc: seoDesc.value,
				categories: $$('input[type="checkbox"]:checked', categoryWrap).map(function (input) { return parseInt(input.value, 10); })
			};
			api('blog/post', { method: 'POST', body: { post: payload } }).then(function (result) {
				toast('Article saved.', 'success');
				if (close) {
					blogState.editing = null;
					refreshBlog();
				} else {
					blogState.editing = result.post;
					refreshBlog();
				}
			}).catch(function (error) { toast(error.message, 'error'); });
		}

		return box;
	}

	/* ------------------------------------------------------------------
	 * SEO
	 * ------------------------------------------------------------------ */

	function renderSeo() {
		state.doc = 'seo';
		var wrap = el('div', { class: 'tusb-stack' });

		wrap.appendChild(spinner('Checking SEO…'));
		Promise.all([loadDoc('seo'), api('seo')]).then(function (results) {
			wrap.innerHTML = '';
			var report = results[1];

			var banner = el('div', { class: 'tusb-callout ' + (report.prints_meta ? '' : 'tusb-callout--attention') });
			if (report.prints_meta) {
				banner.appendChild(el('strong', { text: 'Site Manager is handling SEO output. ' }));
				banner.appendChild(el('span', { text: 'Titles, descriptions, Open Graph and schema are generated here, with no duplicate tags.' }));
			} else {
				banner.appendChild(el('strong', { text: 'Another SEO plugin is active: ' + report.other_plugins.join(', ') + '. ' }));
				banner.appendChild(el('span', { text: 'Site Manager will not print duplicate meta tags. Your values here are passed to that plugin where supported. Nothing has been overwritten.' }));
			}
			wrap.appendChild(banner);

			if (!report.blog_public) {
				wrap.appendChild(el('div', { class: 'tusb-callout tusb-callout--attention' }, [
					el('strong', { text: 'Search engines are currently blocked from this site. ' }),
					el('span', { text: 'This is correct for staging. Before launch, uncheck “Discourage search engines” in Settings → Reading.' }),
					el('a', { class: 'tusb-link', href: T.adminUrl + 'options-reading.php', text: 'Open Reading settings →' })
				]));
			}

			var stats = el('div', { class: 'tusb-stats' });
			statCard(stats, 'Articles & pages', report.posts, '');
			statCard(stats, 'Missing SEO titles', report.missing_title, 'warn');
			statCard(stats, 'Missing descriptions', report.missing_desc, 'warn');
			statCard(stats, 'Images missing alt text', report.missing_alt, 'warn');
			wrap.appendChild(stats);

			wrap.appendChild(el('div', { class: 'tusb-toolbar' }, [
				el('a', { class: 'button', href: report.sitemap, target: '_blank', rel: 'noopener', text: 'Open XML sitemap ↗' }),
				el('a', { class: 'button', href: T.links.permalinks, text: 'Permalink settings' })
			]));
			wrap.appendChild(el('p', { class: 'tusb-help', text: 'Existing URLs are never changed by Site Manager. Current permalink structure: ' + (report.urls_locked || 'plain') + '. Change it only if you have a redirect plan.' }));

			wrap.appendChild(el('h2', { class: 'tusb-h2', text: 'Site-wide defaults' }));
			ensureDraft('seo');
			wrap.appendChild(renderFields(results[0].schema.fields, state.draft, '', 'seo'));

			if (state.dirty) {
				wrap.appendChild(el('div', { class: 'tusb-inline-actions' }, [
					el('button', { class: 'button button-primary', type: 'button', text: 'Save & publish SEO defaults', onclick: function () {
						saveDraft().then(function () { publishDoc(); }).catch(function () {});
					} })
				]));
			}
			updateSaveBar();
		}).catch(function (error) {
			wrap.innerHTML = '';
			wrap.appendChild(el('p', { class: 'tusb-error', text: error.message }));
		});

		return wrap;
	}

	function statCard(parent, label, value, tone) {
		parent.appendChild(el('div', { class: 'tusb-stat' + (value && tone === 'warn' ? ' is-warn' : '') }, [
			el('span', { class: 'tusb-stat__value', text: String(value) }),
			el('span', { class: 'tusb-stat__label', text: label })
		]));
	}

	/* ------------------------------------------------------------------
	 * Media
	 * ------------------------------------------------------------------ */

	var mediaState = { data: null, search: '', page: 1, selected: null, alt: '' };

	function renderMedia() {
		var wrap = el('div', { class: 'tusb-stack' });

		if (!mediaState.data) {
			wrap.appendChild(spinner('Loading images…'));
			api('media?page=' + mediaState.page + '&search=' + encodeURIComponent(mediaState.search)).then(function (data) {
				mediaState.data = data;
				render();
			}).catch(function (error) {
				wrap.appendChild(el('p', { class: 'tusb-error', text: error.message }));
			});
			return wrap;
		}

		var data = mediaState.data;
		var search = el('input', { type: 'search', placeholder: 'Search images…', value: mediaState.search });
		search.addEventListener('keydown', function (event) {
			if (event.key === 'Enter') {
				mediaState.search = search.value;
				mediaState.page = 1;
				mediaState.data = null;
				render();
			}
		});

		wrap.appendChild(el('div', { class: 'tusb-toolbar' }, [
			search,
			el('a', { class: 'button', href: T.links.media, text: 'Upload in Media Library' })
		]));

		var grid = el('div', { class: 'tusb-mediagrid' });
		data.items.forEach(function (image) {
			var button = el('button', {
				class: 'tusb-mediaitem' + (mediaState.selected === image.id ? ' is-selected' : ''),
				type: 'button',
				onclick: function () {
					mediaState.selected = image.id;
					mediaState.alt = image.alt;
					render();
				}
			}, [
				image.thumb ? el('img', { src: image.thumb, alt: '' }) : el('span', { class: 'tusb-mediaitem__none', text: 'No preview' }),
				el('span', { class: 'tusb-mediaitem__meta' }, [
					el('span', { class: 'tusb-mediaitem__name', text: image.title || ('#' + image.id) }),
					image.missing_alt ? el('span', { class: 'tusb-pill tusb-pill--draft', text: 'No alt text' }) : null
				])
			]);
			grid.appendChild(button);
		});
		wrap.appendChild(grid);

		if (mediaState.selected) {
			var image = data.items.filter(function (item) { return item.id === mediaState.selected; })[0];
			if (image) {
				var panel = el('div', { class: 'tusb-panel' });
				panel.appendChild(el('h2', { class: 'tusb-panel__title', text: image.title || ('Image #' + image.id) }));
				if (image.thumb) {
					panel.appendChild(el('img', { class: 'tusb-mediapreview', src: image.thumb, alt: '' }));
				}
				panel.appendChild(el('p', { class: 'tusb-help', text: [image.width + '×' + image.height, image.filesize, image.mime].filter(Boolean).join(' · ') }));

				var altInput = el('input', { type: 'text', value: image.alt, placeholder: 'Describe the image for screen readers' });
				panel.appendChild(el('div', { class: 'tusb-field' }, [
					el('label', { class: 'tusb-field__label', text: 'Alt text' }),
					altInput,
					el('p', { class: 'tusb-help', text: 'Alt text is required for accessibility and SEO. Describe what the image shows, not its filename.' })
				]));

				if (image.used_in && image.used_in.length) {
					panel.appendChild(el('p', { class: 'tusb-help', text: 'Used in: ' + image.used_in.map(function (usage) { return usage.label; }).join(', ') }));
				} else {
					panel.appendChild(el('p', { class: 'tusb-help', text: 'Not used in Site Manager content.' }));
				}

				panel.appendChild(el('div', { class: 'tusb-panel__actions' }, [
					el('button', {
						class: 'button button-primary',
						type: 'button',
						text: 'Save alt text',
						onclick: function () {
							api('media/update', { method: 'POST', body: { updates: [{ id: image.id, alt: altInput.value }] } }).then(function () {
								toast('Alt text saved.', 'success');
								mediaState.data = null;
								render();
							}).catch(function (error) { toast(error.message, 'error'); });
						}
					}),
					el('button', {
						class: 'button',
						type: 'button',
						text: 'Replace image everywhere',
						onclick: function () {
							if (!window.wp || !window.wp.media) {
								return;
							}
							var frame = window.wp.media({ title: 'Choose the replacement image', library: { type: 'image' }, button: { text: 'Replace' }, multiple: false });
							frame.on('select', function () {
								var attachment = frame.state().get('selection').first().toJSON();
								if (!window.confirm('Replace image #' + image.id + ' with “' + attachment.title + '” in all Site Manager content? The old file is kept on the server.')) {
									return;
								}
								api('media/replace', { method: 'POST', body: { old_id: image.id, new_id: attachment.id } }).then(function (result) {
									toast(result.message, 'success');
									mediaState.data = null;
									render();
								}).catch(function (error) { toast(error.message, 'error'); });
							});
							frame.open();
						}
					})
				]));
				wrap.appendChild(panel);
			}
		}

		if (data.pages > 1) {
			var pager = el('div', { class: 'tusb-pager' });
			for (var page = 1; page <= data.pages; page++) {
				(function (pageNumber) {
					pager.appendChild(el('button', {
						class: 'button' + (pageNumber === data.page ? ' button-primary' : ''),
						type: 'button',
						text: String(pageNumber),
						onclick: function () {
							mediaState.page = pageNumber;
							mediaState.data = null;
							render();
						}
					}));
				})(page);
			}
			wrap.appendChild(pager);
		}

		return wrap;
	}

	/* ------------------------------------------------------------------
	 * Backups
	 * ------------------------------------------------------------------ */

	var backupState = { data: null, busy: false };

	function renderBackups() {
		var wrap = el('div', { class: 'tusb-stack' });

		if (!backupState.data) {
			wrap.appendChild(spinner('Loading backups…'));
			api('backups').then(function (data) {
				backupState.data = data;
				render();
			}).catch(function (error) {
				wrap.appendChild(el('p', { class: 'tusb-error', text: error.message }));
			});
			return wrap;
		}

		var data = backupState.data;

		wrap.appendChild(el('div', { class: 'tusb-toolbar' }, [
			el('span', { class: 'tusb-toolbar__hint', text: 'Backups are created automatically before every publish, and daily. Stored in ' + data.location }),
			el('div', {}, [
				el('button', {
					class: 'button button-primary',
					type: 'button',
					text: 'Create backup now',
					disabled: backupState.busy,
					onclick: function () {
						backupState.busy = true;
						api('backups', { method: 'POST', body: { reason: 'manual' } }).then(function () {
							toast('Backup created.', 'success');
							backupState.busy = false;
							backupState.data = null;
							render();
						}).catch(function (error) {
							backupState.busy = false;
							toast(error.message, 'error');
						});
					}
				}),
				el('button', {
					class: 'button',
					type: 'button',
					style: 'margin-left:8px',
					text: 'Download current content',
					onclick: function () {
						window.open(T.restUrl + 'backups/download-current?_wpnonce=' + encodeURIComponent(T.nonce), '_blank');
					}
				})
			])
		]));

		if (data.next) {
			wrap.appendChild(el('p', { class: 'tusb-help', text: 'Next automatic backup: ' + new Date(data.next * 1000).toLocaleString() }));
		}

		var table = el('table', { class: 'tusb-table' });
		table.appendChild(el('thead', {}, [el('tr', {}, [
			el('th', { scope: 'col', text: 'Created' }),
			el('th', { scope: 'col', text: 'Reason' }),
			el('th', { scope: 'col', text: 'Size' }),
			el('th', { scope: 'col', text: 'By' }),
			el('th', { scope: 'col', text: 'Actions' })
		])]));
		var body = el('tbody');
		if (!data.backups.length) {
			body.appendChild(el('tr', {}, [el('td', { colspan: '5' }, [el('p', { class: 'tusb-help', text: 'No backups yet. Create one before making large changes.' })])]));
		}
		data.backups.forEach(function (backup) {
			body.appendChild(el('tr', {}, [
				el('td', { text: backup.created_label }),
				el('td', { text: backup.reason }),
				el('td', { text: backup.size_label }),
				el('td', { text: backup.user_name }),
				el('td', { class: 'tusb-table__actions' }, [
					el('button', {
						class: 'button button-small',
						type: 'button',
						text: 'Restore',
						onclick: function () {
							if (!window.confirm('Restore the backup from ' + backup.created_label + '?\n\nA safety backup of the current content is created first. The snapshot is loaded into your drafts, so the live site changes only when you press Publish changes.')) {
								return;
							}
							api('backups/' + encodeURIComponent(backup.id) + '/restore', { method: 'POST' }).then(function (result) {
								toast('Restored ' + result.imported + ' document(s) into your drafts. Check them, then press Publish changes. Safety backup: ' + result.safety.id, 'success');
								Object.keys(state.docs).forEach(function (key) { delete state.docs[key]; });
								backupState.data = null;
								render();
							}).catch(function (error) { toast(error.message, 'error'); });
						}
					}),
					el('button', {
						class: 'button button-small',
						type: 'button',
						text: 'Download',
						onclick: function () {
							window.open(T.restUrl + 'backups/' + encodeURIComponent(backup.id) + '/download?_wpnonce=' + encodeURIComponent(T.nonce), '_blank');
						}
					}),
					el('button', {
						class: 'button-link',
						type: 'button',
						style: 'color:#b32d2e;margin-left:8px',
						text: 'Delete',
						onclick: function () {
							if (!window.confirm('Delete this backup file permanently?')) {
								return;
							}
							api('backups/' + encodeURIComponent(backup.id), { method: 'DELETE' }).then(function () {
								backupState.data = null;
								render();
							}).catch(function (error) { toast(error.message, 'error'); });
						}
					})
				])
			]));
		});
		table.appendChild(body);
		wrap.appendChild(table);

		var fileInput = el('input', { type: 'file', accept: '.json,application/json' });
		wrap.appendChild(el('div', { class: 'tusb-panel' }, [
			el('h2', { class: 'tusb-panel__title', text: 'Import a backup file' }),
			el('p', { class: 'tusb-help', text: 'Use this to move content from staging to live, or to recover a downloaded backup. A safety backup is created first, and the imported content arrives as a draft — publish when you have checked it.' }),
			el('div', { class: 'tusb-inline-form' }, [
				fileInput,
				el('button', {
					class: 'button',
					type: 'button',
					text: 'Upload & restore',
					onclick: function () {
						if (!fileInput.files || !fileInput.files[0]) {
							toast('Choose a backup file first.', 'error');
							return;
						}
						if (!window.confirm('Restore from “' + fileInput.files[0].name + '”? A safety backup is created first.')) {
							return;
						}
						var form = new FormData();
						form.append('backup', fileInput.files[0]);
						fetch(T.restUrl + 'backups/upload', {
							method: 'POST',
							headers: { 'X-WP-Nonce': T.nonce },
							credentials: 'same-origin',
							body: form
						}).then(function (response) {
							return response.json().then(function (json) {
								if (!response.ok) {
									throw new Error(json.message || 'Upload failed.');
								}
								return json;
							});
						}).then(function () {
							toast('Backup imported into your drafts. Check the pages, then press Publish changes.', 'success');
							Object.keys(state.docs).forEach(function (key) { delete state.docs[key]; });
							backupState.data = null;
							render();
						}).catch(function (error) { toast(error.message, 'error'); });
					}
				})
			])
		]));

		return wrap;
	}

	/* ------------------------------------------------------------------
	 * Revision history
	 * ------------------------------------------------------------------ */

	var revisionState = { doc: 'home', data: null, preview: null };

	function renderRevisions() {
		var wrap = el('div', { class: 'tusb-stack' });
		var docs = (state.boot && state.boot.defaults.doc_labels) || {};
		var select = el('select', { 'aria-label': 'Choose content area' });
		Object.keys(docs).forEach(function (key) {
			var option = el('option', { value: key, text: docs[key] });
			if (key === revisionState.doc) {
				option.selected = true;
			}
			select.appendChild(option);
		});
		select.addEventListener('change', function () {
			revisionState.doc = select.value;
			revisionState.data = null;
			revisionState.preview = null;
			render();
		});
		wrap.appendChild(el('div', { class: 'tusb-toolbar' }, [select]));

		if (!revisionState.data) {
			wrap.appendChild(spinner('Loading versions…'));
			api('docs/' + encodeURIComponent(revisionState.doc) + '/revisions').then(function (data) {
				revisionState.data = data;
				render();
			}).catch(function (error) {
				wrap.appendChild(el('p', { class: 'tusb-error', text: error.message }));
			});
			return wrap;
		}

		var revisions = revisionState.data.revisions || [];
		if (!revisions.length) {
			wrap.appendChild(el('p', { class: 'tusb-help', text: 'No saved versions yet. Versions are created every time you save.' }));
			return wrap;
		}

		var table = el('table', { class: 'tusb-table' });
		table.appendChild(el('thead', {}, [el('tr', {}, [
			el('th', { scope: 'col', text: 'When' }),
			el('th', { scope: 'col', text: 'What' }),
			el('th', { scope: 'col', text: 'By' }),
			el('th', { scope: 'col', text: 'Size' }),
			el('th', { scope: 'col', text: 'Actions' })
		])]));
		var body = el('tbody');
		revisions.forEach(function (revision) {
			body.appendChild(el('tr', { class: revision.is_live ? 'is-live' : '' }, [
				el('td', {}, [
					el('strong', { text: new Date(revision.saved * 1000).toLocaleString() }),
					el('div', { class: 'tusb-help', text: '#' + revision.id + (revision.is_live ? ' · live now' : '') + (revision.is_current ? ' · current draft' : '') })
				]),
				el('td', { text: revision.label || '—' }),
				el('td', { text: revision.user_name }),
				el('td', { text: summaryOf(revision.counts) }),
				el('td', { class: 'tusb-table__actions' }, [
					el('button', {
						class: 'button button-small',
						type: 'button',
						text: 'View',
						onclick: function () {
							api('revisions/' + encodeURIComponent(revisionState.doc) + '/' + revision.id).then(function (detail) {
								revisionState.preview = detail;
								render();
							}).catch(function (error) { toast(error.message, 'error'); });
						}
					}),
					revision.is_live ? null : el('button', {
						class: 'button button-small',
						type: 'button',
						text: 'Restore',
						onclick: function () {
							if (!window.confirm(t('confirmRestore'))) {
								return;
							}
							api('docs/' + encodeURIComponent(revisionState.doc) + '/restore', { method: 'POST', body: { revision_id: revision.id } }).then(function () {
								toast('Version restored into the draft. Publish when you are ready.', 'success');
								delete state.docs[revisionState.doc];
								revisionState.data = null;
								render();
							}).catch(function (error) { toast(error.message, 'error'); });
						}
					})
				])
			]));
		});
		table.appendChild(body);
		wrap.appendChild(table);

		if (revisionState.preview) {
			var panel = el('div', { class: 'tusb-panel' });
			panel.appendChild(el('h2', { class: 'tusb-panel__title', text: 'Version #' + revisionState.preview.id + ' — ' + (revisionState.preview.label || 'snapshot') }));
			panel.appendChild(el('pre', { class: 'tusb-code', text: JSON.stringify(revisionState.preview.payload, null, 2).slice(0, 20000) }));
			wrap.appendChild(panel);
		}

		return wrap;
	}

	function summaryOf(counts) {
		if (!counts) {
			return '—';
		}
		if (counts.sections !== undefined) {
			return counts.sections + ' sections (' + counts.enabled + ' visible)';
		}
		if (counts.items !== undefined) {
			return counts.items + ' items';
		}
		if (counts.fields !== undefined) {
			return counts.fields + ' fields';
		}
		return '—';
	}

	/* ------------------------------------------------------------------
	 * Health & help
	 * ------------------------------------------------------------------ */

	function renderHealth() {
		var wrap = el('div', { class: 'tusb-stack' });
		var health = state.boot.health;

		wrap.appendChild(el('div', { class: 'tusb-callout ' + (health.ok ? '' : 'tusb-callout--attention') }, [
			el('strong', { text: health.ok ? 'All requirements are met. ' : 'Some requirements need attention. ' }),
			el('span', { text: health.ok ? 'Editing and publishing should work normally. Your content is stored in the WordPress database.' : 'Content editing may fail until these are fixed. Your existing website is not affected.' })
		]));

		var table = el('table', { class: 'tusb-table' });
		table.appendChild(el('thead', {}, [el('tr', {}, [
			el('th', { scope: 'col', text: 'Check' }),
			el('th', { scope: 'col', text: 'Found' }),
			el('th', { scope: 'col', text: 'Needs' }),
			el('th', { scope: 'col', text: 'Status' })
		])]));
		var body = el('tbody');
		Object.keys(health.checks).forEach(function (key) {
			var check = health.checks[key];
			body.appendChild(el('tr', {}, [
				el('td', { text: check.label }),
				el('td', { text: check.value }),
				el('td', { text: check.need }),
				el('td', {}, [el('span', { class: 'tusb-pill tusb-pill--' + (check.ok ? 'publish' : 'draft'), text: check.ok ? 'OK' : 'Action needed' })])
			]));
		});
		table.appendChild(body);
		wrap.appendChild(table);

		wrap.appendChild(el('h2', { class: 'tusb-h2', text: 'Environment' }));
		wrap.appendChild(el('ul', { class: 'tusb-plainlist' }, [
			el('li', { text: 'Theme: ' + health.theme.name + ' ' + health.theme.version + (health.theme.is_block ? ' (block theme)' : '') }),
			el('li', { text: 'PHP: ' + health.php_version + ' · memory ' + health.memory_limit + ' · upload limit ' + health.max_upload }),
			el('li', { text: 'SEO plugins detected: ' + (health.conflicts.length ? health.conflicts.join(', ') : 'none') }),
			el('li', { text: 'Active plugins: ' + (Object.keys(health.active_plugins).length ? Object.values(health.active_plugins).join(', ') : 'none') })
		]));

		wrap.appendChild(el('h2', { class: 'tusb-h2', text: 'Quick self-test' }));
		var results = el('div', { class: 'tusb-testresults' });
		wrap.appendChild(el('div', { class: 'tusb-inline-actions' }, [
			el('button', {
				class: 'button button-primary',
				type: 'button',
				text: 'Run self-test',
				onclick: function () {
					results.innerHTML = '';
					results.appendChild(spinner('Running tests…'));
					runSelfTest(results);
				}
			})
		]));
		wrap.appendChild(results);

		wrap.appendChild(el('h2', { class: 'tusb-h2', text: 'Quick help' }));
		var help = [
			['Nothing is visible on the site after publishing', 'Your theme may keep its own header/footer and page content. Use the TrustUsBro blocks in the block editor, or the [trustusbro_page doc="home"] shortcode, to place the editable sections wherever you want them.'],
			['The homepage looks empty', 'Enable “Use Site Manager sections for the front page” in Design settings, or insert the “TrustUsBro page sections” block into your front page.'],
			['I want to undo a change', 'Open Revision history, pick the version and press Restore. Nothing goes live until you publish.'],
			['I made a mistake and already published', 'Open Backups and restore the backup that was created automatically before publishing.'],
			['Another SEO plugin is active', 'That is fine. Site Manager detects it and stops printing duplicate tags.'],
			['Do I lose content if I disable the plugin?', 'No. All content lives in the WordPress database and is left untouched. Re-enabling restores the dashboard exactly as it was.']
		];
		help.forEach(function (row) {
			var details = el('details', { class: 'tusb-panel' });
			details.appendChild(el('summary', { text: row[0] }));
			details.appendChild(el('p', { text: row[1] }));
			wrap.appendChild(details);
		});

		return wrap;
	}

	function runSelfTest(container) {
		var steps = [];
		var docKey = 'home';

		function record(name, fn) {
			steps.push(function () {
				var started = Date.now();
				return fn().then(function (detail) {
					return { name: name, ok: true, detail: detail || '', ms: Date.now() - started };
				}).catch(function (error) {
					return { name: name, ok: false, detail: error.message, ms: Date.now() - started };
				});
			});
		}

		record('Read content from the database', function () {
			return api('docs/' + docKey).then(function (data) {
				return (data.draft.sections || []).length + ' sections in the draft, ' + (data.published.sections || []).length + ' published';
			});
		});

		record('Save a draft (non-destructive test write)', function () {
			return api('docs/' + docKey).then(function (data) {
				return api('docs/' + docKey + '/draft', {
					method: 'POST',
					body: { payload: data.draft, label: 'Self-test (no content change)' }
				}).then(function (result) {
					delete state.docs[docKey];
					return 'Draft revision #' + result.draft_version + ' written';
				});
			});
		});

		record('Create and read a backup', function () {
			return api('backups', { method: 'POST', body: { reason: 'self-test' } }).then(function (entry) {
				return api('backups/' + encodeURIComponent(entry.id)).then(function () {
					return 'Backup ' + entry.id + ' (' + entry.docs + ' documents) verified';
				});
			});
		});

		record('Media library is reachable', function () {
			return api('media?per_page=1').then(function (data) {
				return data.total + ' images in the library';
			});
		});

		record('SEO module reports correctly', function () {
			return api('seo').then(function (report) {
				return (report.prints_meta ? 'Site Manager prints meta tags' : 'Deferring to ' + report.other_plugins.join(', '));
			});
		});

		var chain = Promise.resolve();
		var list = el('ul', { class: 'tusb-plainlist' });
		steps.forEach(function (step) {
			chain = chain.then(function () {
				return step().then(function (result) {
					list.appendChild(el('li', {}, [
						el('span', { class: 'tusb-pill tusb-pill--' + (result.ok ? 'publish' : 'draft'), text: result.ok ? 'Pass' : 'Fail' }),
						el('span', { text: ' ' + result.name + ' — ' + result.detail + ' (' + result.ms + ' ms)' })
					]));
				});
			});
		});
		chain.then(function () {
			container.innerHTML = '';
			container.appendChild(list);
			container.appendChild(el('p', { class: 'tusb-help', text: 'The self-test writes one extra draft revision labelled “Self-test”. It does not change your published content.' }));
		});
	}

	/* ------------------------------------------------------------------
	 * Boot
	 * ------------------------------------------------------------------ */

	function boot() {
		api('bootstrap').then(function (data) {
			state.boot = data;
			if (!data.user.can_manage) {
				app.innerHTML = '';
				app.appendChild(el('p', { class: 'tusb-error', text: 'You do not have permission to manage this website. Ask an administrator for the “Manage website content” permission.' }));
				return;
			}
			if (state.doc && VIEW_TO_DOC[state.view] !== state.doc && state.view !== 'pages') {
				state.doc = VIEW_TO_DOC[state.view] || '';
			}
			render();
		}).catch(function (error) {
			app.innerHTML = '';
			app.appendChild(el('div', { class: 'tusb-error' }, [
				el('strong', { text: 'The Site Manager could not load. ' }),
				el('span', { text: error.message || 'Please reload the page.' })
			]));
		});
	}

	window.addEventListener('beforeunload', function (event) {
		if (state.dirty) {
			event.preventDefault();
			event.returnValue = '';
			return '';
		}
	});

	document.addEventListener('keydown', function (event) {
		var meta = event.ctrlKey || event.metaKey;
		if (meta && event.key.toLowerCase() === 's') {
			event.preventDefault();
			if (state.doc && state.dirty) {
				saveDraft();
			}
		}
	});

	boot();
})();
