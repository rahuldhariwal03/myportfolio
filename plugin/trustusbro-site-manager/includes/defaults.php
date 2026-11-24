<?php
/**
 * Starter and demo content.
 *
 * Starter content is deliberately structural: it creates the sections the brief
 * requires but contains no invented facts about the business (no fake clients,
 * metrics, testimonials or contact details). Those must be supplied by the
 * owner. Demo content is available on demand from the dashboard so the owner
 * can see the layout before entering real content.
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

/**
 * A sensible internal link target, using an existing page when possible.
 *
 * @param string $path Page path.
 * @param string $fallback Fallback URL.
 * @return string
 */
function tusb_link( $path, $fallback = '' ) {
	$page = get_page_by_path( $path );
	if ( $page instanceof WP_Post && 'publish' === $page->post_status ) {
		return get_permalink( $page );
	}
	return $fallback ? $fallback : home_url( '/' . trim( $path, '/' ) . '/' );
}

/**
 * Starter content for a fresh install.
 *
 * @return array
 */
function tusb_seed_content() {
	$home_sections = array();
	foreach ( array( 'hero', 'services', 'industries', 'philosophy', 'process', 'case_studies', 'testimonials', 'faq', 'cta', 'contact' ) as $index => $type ) {
		$home_sections[] = array_merge(
			array(
				'id'      => 'seed-' . $type,
				'type'    => $type,
				'enabled' => true,
			),
			TUSB_Schema::field_defaults( TUSB_Schema::section( 'home', $type )['fields'] )
		);
	}

	$about_sections = array();
	foreach ( array( 'intro', 'values', 'timeline', 'cta' ) as $type ) {
		$about_sections[] = array_merge(
			array(
				'id'      => 'seed-' . $type,
				'type'    => $type,
				'enabled' => true,
			),
			TUSB_Schema::field_defaults( TUSB_Schema::section( 'about', $type )['fields'] )
		);
	}

	return array(
		'home'         => array( 'sections' => $home_sections ),
		'about'        => array( 'sections' => $about_sections ),
		'services'     => array( 'items' => array() ),
		'industries'   => array( 'items' => array() ),
		'case_studies' => array( 'items' => array() ),
		'testimonials' => array( 'items' => array() ),
		'faq'          => array( 'items' => array() ),
		'header'       => array(
			'logo'         => 0,
			'logo_text'    => get_bloginfo( 'name' ),
			'logo_url'     => home_url( '/' ),
			'menu_items'   => array(
				array( 'id' => 'menu-home', 'label' => __( 'Home', 'trustusbro-site-manager' ), 'url' => home_url( '/' ), 'children' => array() ),
				array( 'id' => 'menu-services', 'label' => __( 'Services', 'trustusbro-site-manager' ), 'url' => home_url( '/#tusb-seed-services' ), 'children' => array() ),
				array( 'id' => 'menu-work', 'label' => __( 'Work', 'trustusbro-site-manager' ), 'url' => home_url( '/#tusb-seed-case_studies' ), 'children' => array() ),
				array( 'id' => 'menu-about', 'label' => __( 'About', 'trustusbro-site-manager' ), 'url' => tusb_link( 'about' ), 'children' => array() ),
				array( 'id' => 'menu-blog', 'label' => __( 'Blog', 'trustusbro-site-manager' ), 'url' => get_permalink( get_option( 'page_for_posts' ) ) ? get_permalink( get_option( 'page_for_posts' ) ) : home_url( '/blog/' ), 'children' => array() ),
				array( 'id' => 'menu-contact', 'label' => __( 'Contact', 'trustusbro-site-manager' ), 'url' => home_url( '/#tusb-seed-contact' ), 'children' => array() ),
			),
			'cta'          => array( 'label' => __( 'Start a project', 'trustusbro-site-manager' ), 'url' => home_url( '/#tusb-seed-contact' ), 'style' => 'primary' ),
			'sticky'       => true,
			'transparent'  => false,
			'mobile_label' => __( 'Menu', 'trustusbro-site-manager' ),
			'use_wp_menu'  => false,
		),
		'footer'       => array(
			'logo'        => 0,
			'tagline'     => get_bloginfo( 'name' ),
			'description' => __( 'Describe your agency in one or two sentences.', 'trustusbro-site-manager' ),
			'social'      => array(),
			'columns'     => array(
				array(
					'id'    => 'footer-nav',
					'title' => __( 'Navigate', 'trustusbro-site-manager' ),
					'links' => array(
						array( 'id' => 'f-home', 'label' => __( 'Home', 'trustusbro-site-manager' ), 'url' => home_url( '/' ) ),
						array( 'id' => 'f-about', 'label' => __( 'About', 'trustusbro-site-manager' ), 'url' => tusb_link( 'about' ) ),
						array( 'id' => 'f-work', 'label' => __( 'Work', 'trustusbro-site-manager' ), 'url' => home_url( '/#tusb-seed-case_studies' ) ),
					),
				),
				array(
					'id'    => 'footer-services',
					'title' => __( 'Services', 'trustusbro-site-manager' ),
					'links' => array(),
				),
				array(
					'id'    => 'footer-industries',
					'title' => __( 'Industries', 'trustusbro-site-manager' ),
					'links' => array(),
				),
			),
			'email'       => '',
			'phone'       => '',
			'address'     => '',
			'copyright'   => '© {year} {site}',
			'legal_links' => array(
				array( 'id' => 'legal-privacy', 'label' => __( 'Privacy policy', 'trustusbro-site-manager' ), 'url' => tusb_link( 'privacy-policy' ) ),
			),
		),
		'contact'      => array(
			'email'     => get_option( 'admin_email' ),
			'phone'     => '',
			'whatsapp'  => '',
			'address'   => '',
			'hours'     => '',
			'map_embed' => '',
			'recipient' => get_option( 'admin_email' ),
			'social'    => array(),
		),
		'seo'          => array(
			'title_suffix'     => ' | {site}',
			'meta_description' => get_bloginfo( 'description' ),
			'og_image'         => 0,
			'twitter_handle'   => '',
			'organization'     => get_bloginfo( 'name' ),
			'logo'             => 0,
			'noindex'          => false,
			'schema_types'     => array(),
		),
		'design'       => array(
			'color_text'        => '',
			'color_heading'     => '',
			'color_muted'       => '',
			'color_accent'      => '',
			'color_accent_text' => '',
			'color_surface'     => '',
			'color_border'      => '',
			'color_bg'          => '',
			'font_body'         => '',
			'font_heading'      => '',
			'font_mono'         => '',
			'radius'            => '0',
			'container_width'   => '1280px',
			'section_space'     => '96px',
			'button_style'      => 'square',
			'show_branding'     => false,
			'header_menu'       => '',
			'front_page'        => false,
			'about_page'        => 0,
			'legacy_docs'       => '',
		),
	);
}

/**
 * Demo content, loaded only on explicit user action.
 *
 * @return array
 */
function tusb_demo_content() {
	return array(
		'services' => array(
			'items' => array(
				array(
					'id'      => 'demo-brand',
					'visible' => true,
					'title'   => __( 'Brand strategy', 'trustusbro-site-manager' ),
					'summary' => __( 'Positioning, messaging and identity systems that make a brand easy to recognise and hard to confuse.', 'trustusbro-site-manager' ),
					'icon'    => 'sparkle',
					'features'=> array(
						array( 'id' => 'demo-brand-1', 'text' => __( 'Positioning workshops', 'trustusbro-site-manager' ) ),
						array( 'id' => 'demo-brand-2', 'text' => __( 'Visual identity', 'trustusbro-site-manager' ) ),
					),
				),
				array(
					'id'      => 'demo-web',
					'visible' => true,
					'title'   => __( 'Website design', 'trustusbro-site-manager' ),
					'summary' => __( 'Fast, accessible websites with a clear structure so visitors always know what to do next.', 'trustusbro-site-manager' ),
					'icon'    => 'design',
					'features'=> array(),
				),
				array(
					'id'      => 'demo-growth',
					'visible' => true,
					'title'   => __( 'Growth campaigns', 'trustusbro-site-manager' ),
					'summary' => __( 'Campaign pages, content and measurement that turn attention into enquiries.', 'trustusbro-site-manager' ),
					'icon'    => 'chart',
					'features'=> array(),
				),
			),
		),
		'industries' => array(
			'items' => array(
				array( 'id' => 'demo-retail', 'visible' => true, 'title' => __( 'Retail', 'trustusbro-site-manager' ), 'summary' => __( 'Storefronts and catalogues that feel effortless on a phone.', 'trustusbro-site-manager' ) ),
				array( 'id' => 'demo-health', 'visible' => true, 'title' => __( 'Healthcare', 'trustusbro-site-manager' ), 'summary' => __( 'Calm, trustworthy information for people making important decisions.', 'trustusbro-site-manager' ) ),
				array( 'id' => 'demo-edu', 'visible' => true, 'title' => __( 'Education', 'trustusbro-site-manager' ), 'summary' => __( 'Programme pages and portals that keep learners on track.', 'trustusbro-site-manager' ) ),
			),
		),
		'case_studies' => array(
			'items' => array(
				array(
					'id'      => 'demo-case-1',
					'visible' => true,
					'title'   => __( 'Example project one', 'trustusbro-site-manager' ),
					'client'  => __( 'Sample client', 'trustusbro-site-manager' ),
					'summary' => __( 'Replace this summary with what the client needed, what you did and why it worked.', 'trustusbro-site-manager' ),
					'result'  => __( 'Add the headline outcome', 'trustusbro-site-manager' ),
					'tags'    => __( 'Strategy, UX, Web', 'trustusbro-site-manager' ),
				),
				array(
					'id'      => 'demo-case-2',
					'visible' => true,
					'title'   => __( 'Example project two', 'trustusbro-site-manager' ),
					'client'  => __( 'Sample client', 'trustusbro-site-manager' ),
					'summary' => __( 'A second placeholder case study so you can see how two cards sit side by side.', 'trustusbro-site-manager' ),
					'result'  => '',
					'tags'    => __( 'Brand, Design', 'trustusbro-site-manager' ),
				),
			),
		),
		'testimonials' => array(
			'items' => array(
				array(
					'id'     => 'demo-quote-1',
					'visible'=> true,
					'quote'  => __( 'Replace this with a real client quote. Do not publish placeholder testimonials.', 'trustusbro-site-manager' ),
					'name'   => __( 'Client name', 'trustusbro-site-manager' ),
					'role'   => __( 'Role, company', 'trustusbro-site-manager' ),
					'rating' => 5,
				),
			),
		),
		'faq' => array(
			'items' => array(
				array(
					'id'       => 'demo-faq-1',
					'visible'  => true,
					'question' => __( 'What does working together look like?', 'trustusbro-site-manager' ),
					'answer'   => __( 'Answer this with your real process. You can add bold text and links.', 'trustusbro-site-manager' ),
				),
				array(
					'id'       => 'demo-faq-2',
					'visible'  => true,
					'question' => __( 'How long does a project take?', 'trustusbro-site-manager' ),
					'answer'   => __( 'Give an honest, practical answer here.', 'trustusbro-site-manager' ),
				),
			),
		),
	);
}
