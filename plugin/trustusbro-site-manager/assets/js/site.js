/**
 * TrustUsBro Site Manager — front-end behaviour.
 *
 * Tiny, dependency-free, progressive enhancement only:
 *  - the mobile menu toggle (native <details> fallback is not needed because the
 *    links are also reachable without JS via the mobile nav being present)
 *  - keyboard support for the sticky header offset
 *
 * No tracking, no external requests.
 */
(function () {
	'use strict';

	function ready(fn) {
		if (document.readyState === 'loading') {
			document.addEventListener('DOMContentLoaded', fn);
		} else {
			fn();
		}
	}

	ready(function () {
		var toggle = document.querySelector('.tusb-menu-toggle');
		var mobileNav = document.getElementById('tusb-mobile-nav');

		if (toggle && mobileNav) {
			mobileNav.hidden = true;
			toggle.setAttribute('aria-expanded', 'false');

			toggle.addEventListener('click', function () {
				var open = toggle.getAttribute('aria-expanded') === 'true';
				toggle.setAttribute('aria-expanded', open ? 'false' : 'true');
				mobileNav.hidden = open;
			});

			mobileNav.addEventListener('click', function (event) {
				if (event.target && event.target.tagName === 'A') {
					toggle.setAttribute('aria-expanded', 'false');
					mobileNav.hidden = true;
				}
			});

			document.addEventListener('keydown', function (event) {
				if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
					toggle.setAttribute('aria-expanded', 'false');
					mobileNav.hidden = true;
					toggle.focus();
				}
			});
		}

		// Smooth-scroll to in-page section anchors from the header menu.
		document.addEventListener('click', function (event) {
			var link = event.target.closest ? event.target.closest('a[href*="#tusb-"]') : null;
			if (!link) {
				return;
			}
			var url = new URL(link.href, window.location.href);
			if (url.pathname !== window.location.pathname || url.origin !== window.location.origin) {
				return;
			}
			var target = document.getElementById(url.hash.replace('#', ''));
			if (!target) {
				return;
			}
			event.preventDefault();
			var header = document.querySelector('.tusb-header');
			var offset = header ? header.getBoundingClientRect().height : 0;
			var top = target.getBoundingClientRect().top + window.pageYOffset - offset - 8;
			var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
			window.scrollTo({ top: top, behavior: reduce ? 'auto' : 'smooth' });
			if (history.pushState) {
				history.pushState(null, '', url.hash);
			}
			target.setAttribute('tabindex', '-1');
			target.focus({ preventScroll: true });
		});
	});
})();
