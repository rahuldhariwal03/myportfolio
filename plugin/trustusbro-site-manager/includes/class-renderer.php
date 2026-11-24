<?php
/**
 * Front-end renderer.
 *
 * Turns stored documents into HTML. The markup is deliberately plain: a
 * container, a rectangular grid and typography driven by CSS custom
 * properties, so the approved TrustUsBro look is inherited from the theme
 * rather than re-invented here.
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

/**
 * Renderer.
 */
class TUSB_Renderer {

	/**
	 * Guard so the header is never printed twice.
	 *
	 * @var bool
	 */
	protected $header_rendered = false;

	/**
	 * Guard so the footer is never printed twice.
	 *
	 * @var bool
	 */
	protected $footer_rendered = false;

	/**
	 * Reset the render guards (used by previews and tests).
	 *
	 * @return void
	 */
	public function reset_guards() {
		$this->header_rendered = false;
		$this->footer_rendered = false;
	}

	/**
	 * Register hooks.
	 *
	 * @return void
	 */
	public function hooks() {
		add_shortcode( 'trustusbro_page', array( $this, 'shortcode' ) );
		add_shortcode( 'trustusbro_collection', array( $this, 'shortcode_collection' ) );
		add_filter( 'the_content', array( $this, 'filter_page_content' ), 20 );
		add_action( 'template_redirect', array( $this, 'handle_preview' ), 1 );
		add_filter( 'template_include', array( $this, 'preview_template' ), 99 );
		add_action( 'init', array( $this, 'register_header_footer' ) );
		add_action( 'init', array( $this, 'register_blocks' ) );
		add_filter( 'pre_get_document_title', array( $this, 'preview_title' ), 20 );
	}

	/**
	 * Wire the editable header/footer.
	 *
	 * Three integration points, in order of preference:
	 *  1. `tusb_header` / `tusb_footer` actions — a theme can opt in explicitly.
	 *  2. The `trustusbro/header` and `trustusbro/footer` blocks — place them in a
	 *     template part with the Site Editor. Nothing is injected twice.
	 *  3. Automatic injection on `wp_body_open` / `wp_footer` — only when the owner
	 *     explicitly enables "render header and footer from Site Manager" in
	 *     Design settings. Off by default so an approved theme header is never
	 *     duplicated by surprise.
	 *
	 * @return void
	 */
	public function register_header_footer() {
		add_action( 'tusb_header', array( $this, 'header' ) );
		add_action( 'tusb_footer', array( $this, 'footer' ) );

		if ( '1' !== TUSB_Design::token( 'show_branding', '0' ) ) {
			return;
		}

		add_action( 'wp_body_open', array( $this, 'maybe_render_header' ), 5 );
		add_action( 'wp_footer', array( $this, 'maybe_render_footer' ), 5 );
	}

	/**
	 * Render the header once, if automatic branding is on.
	 *
	 * @return void
	 */
	public function maybe_render_header() {
		if ( $this->header_rendered || is_admin() ) {
			return;
		}
		$this->header();
	}

	/**
	 * Render the footer once, if automatic branding is on.
	 *
	 * @return void
	 */
	public function maybe_render_footer() {
		if ( $this->footer_rendered || is_admin() ) {
			return;
		}
		$this->footer();
	}

	/**
	 * Register dynamic blocks so any section can be inserted into any page with
	 * the native block editor. Server-rendered: the markup always comes from this
	 * renderer, so there is only one source of truth.
	 *
	 * @return void
	 */
	public function register_blocks() {
		if ( ! function_exists( 'register_block_type' ) ) {
			return;
		}

		$blocks = array(
			'trustusbro/page'       => array(
				'title'  => __( 'TrustUsBro page sections', 'trustusbro-site-manager' ),
				'render' => array( $this, 'block_page' ),
				'attrs'  => array(
					'doc' => array(
						'type'    => 'string',
						'default' => 'home',
					),
				),
			),
			'trustusbro/collection' => array(
				'title'  => __( 'TrustUsBro collection', 'trustusbro-site-manager' ),
				'render' => array( $this, 'block_collection' ),
				'attrs'  => array(
					'doc'     => array(
						'type'    => 'string',
						'default' => 'services',
					),
					'columns' => array(
						'type'    => 'number',
						'default' => 3,
					),
					'limit'   => array(
						'type'    => 'number',
						'default' => 0,
					),
				),
			),
			'trustusbro/header'     => array(
				'title'  => __( 'TrustUsBro header', 'trustusbro-site-manager' ),
				'render' => array( $this, 'block_header' ),
				'attrs'  => array(),
			),
			'trustusbro/footer'     => array(
				'title'  => __( 'TrustUsBro footer', 'trustusbro-site-manager' ),
				'render' => array( $this, 'block_footer' ),
				'attrs'  => array(),
			),
		);

		foreach ( $blocks as $name => $config ) {
			register_block_type(
				$name,
				array(
					'api_version'     => 3,
					'title'           => $config['title'],
					'category'        => 'design',
					'icon'            => 'layout',
					'render_callback' => $config['render'],
					'attributes'      => $config['attrs'],
					'supports'        => array(
						'html'  => false,
						'align' => array( 'wide', 'full' ),
					),
				)
			);
		}
	}

	/**
	 * Block: page sections.
	 *
	 * @param array $attrs Attributes.
	 * @return string
	 */
	public function block_page( $attrs ) {
		$doc = isset( $attrs['doc'] ) ? sanitize_key( $attrs['doc'] ) : 'home';
		return $this->render_page( $doc );
	}

	/**
	 * Block: collection grid.
	 *
	 * @param array $attrs Attributes.
	 * @return string
	 */
	public function block_collection( $attrs ) {
		$doc = isset( $attrs['doc'] ) ? sanitize_key( $attrs['doc'] ) : 'services';
		if ( ! in_array( $doc, array( 'services', 'industries', 'case_studies', 'testimonials', 'faq' ), true ) ) {
			return '';
		}
		return $this->collection_grid(
			$doc,
			isset( $attrs['columns'] ) ? (int) $attrs['columns'] : 3,
			isset( $attrs['limit'] ) ? (int) $attrs['limit'] : 0
		);
	}

	/**
	 * Block: header.
	 *
	 * @return string
	 */
	public function block_header() {
		ob_start();
		$this->header();
		return (string) ob_get_clean();
	}

	/**
	 * Block: footer.
	 *
	 * @return string
	 */
	public function block_footer() {
		ob_start();
		$this->footer();
		return (string) ob_get_clean();
	}

	/**
	 * Mark where editor chrome belongs (reserved for future inline editing).
	 *
	 * @param string $type Section type.
	 * @param string $id Section ID.
	 * @return string
	 */
	protected function editor_placeholder( $type, $id ) {
		return '<div class="tusb-editor-slot" data-tusb-slot="' . esc_attr( $id ) . '" data-tusb-slot-type="' . esc_attr( $type ) . '" hidden></div>';
	}

	/**
	 * Shortcode: [trustusbro_page doc="home"].
	 *
	 * @param array $atts Attributes.
	 * @return string
	 */
	public function shortcode( $atts ) {
		$atts = shortcode_atts(
			array(
				'doc' => 'home',
			),
			$atts,
			'trustusbro_page'
		);
		return $this->render_page( sanitize_key( $atts['doc'] ) );
	}

	/**
	 * Shortcode: [trustusbro_collection doc="services" columns="3" limit="6"].
	 *
	 * @param array $atts Attributes.
	 * @return string
	 */
	public function shortcode_collection( $atts ) {
		$atts = shortcode_atts(
			array(
				'doc'     => 'services',
				'columns' => 3,
				'limit'   => 0,
			),
			$atts,
			'trustusbro_collection'
		);
		$doc = sanitize_key( $atts['doc'] );
		if ( ! in_array( $doc, array( 'services', 'industries', 'case_studies', 'testimonials', 'faq' ), true ) ) {
			return '';
		}
		return $this->collection_grid( $doc, (int) $atts['columns'], (int) $atts['limit'] );
	}

	/**
	 * Append rendered sections to the configured pages.
	 *
	 * This is additive only: the theme's own content stays, and Site Manager
	 * output can be switched off per page in Design Settings.
	 *
	 * @param string $content Content.
	 * @return string
	 */
	public function filter_page_content( $content ) {
		if ( is_admin() || ! is_singular() ) {
			return $content;
		}
		$doc_key = $this->doc_for_page( get_queried_object_id() );
		if ( ! $doc_key ) {
			return $content;
		}
		$rendered = $this->render_page( $doc_key );
		if ( '' === $rendered ) {
			return $content;
		}
		return $content . $rendered;
	}

	/**
	 * Which document should render on a given page ID.
	 *
	 * @param int $page_id Page ID.
	 * @return string
	 */
	public function doc_for_page( $page_id ) {
		$page_id   = (int) $page_id;
		$front_id  = (int) TUSB_Design::token( 'front_page', '0' ) ? (int) get_option( 'page_on_front' ) : 0;
		$about_id  = (int) TUSB_Design::token( 'about_page', '0' );

		if ( $page_id && $front_id && $page_id === $front_id ) {
			return 'home';
		}
		if ( $page_id && $about_id && $page_id === $about_id ) {
			return 'about';
		}
		return '';
	}

	/**
	 * Render a whole page document (sections).
	 *
	 * @param string $doc_key Document key.
	 * @param string $state State.
	 * @return string
	 */
	public function render_page( $doc_key, $state = '' ) {
		$doc_key = sanitize_key( $doc_key );
		$doc     = TUSB_Schema::doc( $doc_key );
		if ( ! $doc || 'sections' !== tusb_arr( $doc, 'type' ) ) {
			return '';
		}

		$state  = $this->resolve_state( $state );
		$store  = tusb()->module( 'store' );
		$data   = $store ? $store->resolve( $doc_key, $state ) : TUSB_Schema::defaults( $doc_key );
		$sections = isset( $data['sections'] ) ? $data['sections'] : array();

		$html = '';
		foreach ( $sections as $section ) {
			if ( empty( $section['enabled'] ) ) {
				continue;
			}
			$html .= $this->render_section( $doc_key, $section, $state );
		}

		if ( '' === $html ) {
			return '';
		}

		return '<div class="tusb-page tusb-page--' . esc_attr( $doc_key ) . '" data-tusb-doc="' . esc_attr( $doc_key ) . '">' . $html . '</div>';
	}

	/**
	 * Decide which state to read: previews and editors read drafts.
	 *
	 * @param string $state Requested state.
	 * @return string
	 */
	private function resolve_state( $state = '' ) {
		if ( 'draft' === $state || 'published' === $state ) {
			return $state;
		}
		if ( tusb_is_preview() || is_preview() ) {
			return 'draft';
		}
		if ( is_user_logged_in() && current_user_can( 'edit_posts' ) && isset( $_GET['tusb_state'] ) ) { // phpcs:ignore WordPress.Security.NonceVerification.Recommended
			$requested = sanitize_key( wp_unslash( $_GET['tusb_state'] ) ); // phpcs:ignore WordPress.Security.NonceVerification.Recommended
			if ( 'draft' === $requested ) {
				return 'draft';
			}
		}
		return 'published';
	}

	/**
	 * Render a single section.
	 *
	 * @param string $doc_key Document key.
	 * @param array  $section Section data.
	 * @param string $state State.
	 * @return string
	 */
	public function render_section( $doc_key, $section, $state = 'published' ) {
		$type = isset( $section['type'] ) ? $section['type'] : '';
		$def  = TUSB_Schema::section( $doc_key, $type );
		if ( ! $def ) {
			return '';
		}

		$method = 'section_' . str_replace( '-', '_', $type );
		if ( ! method_exists( $this, $method ) ) {
			$method = 'section_text_block';
			$section = array_merge( array( 'heading' => isset( $def['label'] ) ? $def['label'] : '', 'text' => '' ), $section );
		}

		$id       = isset( $section['id'] ) ? sanitize_key( $section['id'] ) : $type;
		$attrs    = sprintf(
			' class="tusb-section tusb-section--%1$s" id="tusb-%2$s" data-tusb-section="%2$s" data-tusb-type="%1$s"',
			esc_attr( $type ),
			esc_attr( $id )
		);

		$body = $this->$method( $section, $state );

		if ( '' === trim( (string) $body ) ) {
			return '';
		}

		return '<section' . $attrs . '>' . $body . '</section>';
	}

	/*
	 * ---------------------------------------------------------------------
	 * Section renderers
	 * ---------------------------------------------------------------------
	 */

	/**
	 * Hero section.
	 *
	 * @param array  $s Section.
	 * @param string $state State.
	 * @return string
	 */
	protected function section_hero( $s, $state ) {
		$position = isset( $s['image_position'] ) ? $s['image_position'] : 'right';
		$image    = $position !== 'none' ? $this->image( tusb_arr( $s, 'image' ), 'large', 'tusb-hero__media' ) : '';
		$text     = '<div class="tusb-hero__text">';
		$text    .= $this->eyebrow( tusb_arr( $s, 'eyebrow' ), 'hero:eyebrow' );
		$text    .= $this->heading( tusb_arr( $s, 'heading' ), 'h1', 'hero:heading', 'tusb-hero__heading' );
		$text    .= $this->text( tusb_arr( $s, 'text' ), 'hero:text', 'tusb-hero__text-body' );
		$text    .= $this->buttons( tusb_arr( $s, 'buttons', array() ), 'hero:buttons', 'tusb-hero__actions' );
		if ( ! empty( $s['note'] ) ) {
			$text .= '<p class="tusb-note" data-tusb-field="hero:note">' . esc_html( $s['note'] ) . '</p>';
		}
		$text .= '</div>';

		$classes = 'tusb-hero tusb-hero--' . sanitize_html_class( $position );
		if ( '' === $image ) {
			$classes .= ' tusb-hero--no-media';
		}

		return '<div class="' . esc_attr( $classes ) . '"><div class="tusb-container">' . $text . $image . '</div></div>';
	}

	/**
	 * Generic heading + intro + grid of cards from a collection.
	 *
	 * @param array  $s Section.
	 * @param string $doc Collection doc.
	 * @param string $state State.
	 * @param string $extra_class Extra class.
	 * @return string
	 */
	protected function collection_section( $s, $doc, $state, $extra_class = '' ) {
		$store = tusb()->module( 'store' );
		$data  = $store ? $store->resolve( $doc, $state ) : array( 'items' => array() );
		$items = isset( $data['items'] ) ? $data['items'] : array();
		$items = array_values(
			array_filter(
				$items,
				static function ( $item ) {
					return ! isset( $item['visible'] ) || $item['visible'];
				}
			)
		);
		$limit = isset( $s['limit'] ) ? (int) $s['limit'] : 6;
		if ( $limit > 0 ) {
			$items = array_slice( $items, 0, $limit );
		}

		$columns = isset( $s['columns'] ) ? (int) $s['columns'] : 3;
		$columns = max( 1, min( 4, $columns ) );

		$html  = '<div class="tusb-container">';
		$html .= $this->section_head( $s );
		if ( $items ) {
			$html .= '<div class="tusb-grid tusb-grid--' . esc_attr( $columns ) . ' ' . esc_attr( $extra_class ) . '" data-tusb-collection="' . esc_attr( $doc ) . '">';
			foreach ( $items as $item ) {
				$html .= $this->{$this->card_method( $doc )}( $item );
			}
			$html .= '</div>';
		} elseif ( $this->is_editor_context() ) {
			$html .= '<p class="tusb-empty">' . esc_html(
				sprintf(
					/* translators: %s: collection name. */
					__( 'No %s yet. Add your first one in the Site Manager dashboard.', 'trustusbro-site-manager' ),
					strtolower( tusb_doc_label( $doc ) )
				)
			) . '</p>';
		}
		if ( ! empty( $s['button']['label'] ) ) {
			$html .= '<div class="tusb-section__foot">' . $this->button( $s['button'], 'tusb-section:button' ) . '</div>';
		}
		$html .= '</div>';

		return $html;
	}

	/**
	 * Card renderer method for a collection.
	 *
	 * @param string $doc Collection key.
	 * @return string
	 */
	private function card_method( $doc ) {
		$map = array(
			'services'     => 'card_service',
			'industries'   => 'card_industry',
			'case_studies' => 'card_case_study',
			'testimonials' => 'card_testimonial',
			'faq'          => 'card_faq',
		);
		return isset( $map[ $doc ] ) ? $map[ $doc ] : 'card_service';
	}

	/**
	 * Services section.
	 *
	 * @param array  $s Section.
	 * @param string $state State.
	 * @return string
	 */
	protected function section_services( $s, $state ) {
		return $this->collection_section( $s, 'services', $state );
	}

	/**
	 * Industries section.
	 *
	 * @param array  $s Section.
	 * @param string $state State.
	 * @return string
	 */
	protected function section_industries( $s, $state ) {
		return $this->collection_section( $s, 'industries', $state );
	}

	/**
	 * Case studies section.
	 *
	 * @param array  $s Section.
	 * @param string $state State.
	 * @return string
	 */
	protected function section_case_studies( $s, $state ) {
		return $this->collection_section( $s, 'case_studies', $state );
	}

	/**
	 * Testimonials section.
	 *
	 * @param array  $s Section.
	 * @param string $state State.
	 * @return string
	 */
	protected function section_testimonials( $s, $state ) {
		return $this->collection_section( $s, 'testimonials', $state );
	}

	/**
	 * Philosophy section.
	 *
	 * @param array  $s Section.
	 * @param string $state State.
	 * @return string
	 */
	protected function section_philosophy( $s, $state ) {
		$html  = '<div class="tusb-container">';
		$html .= '<div class="tusb-split">';
		$html .= '<div class="tusb-split__main">';
		$html .= $this->section_head( $s );
		$image = $this->image( tusb_arr( $s, 'image' ), 'large', 'tusb-philosophy__media' );
		if ( $image ) {
			$html .= $image;
		}
		$html .= '</div>';

		$principles = tusb_arr( $s, 'principles', array() );
		if ( $principles ) {
			$html .= '<ol class="tusb-principles" data-tusb-repeater="philosophy:principles">';
			$i = 1;
			foreach ( $principles as $p ) {
				$html .= '<li class="tusb-principle">';
				$html .= '<span class="tusb-principle__index">' . esc_html( sprintf( '%02d', $i ) ) . '</span>';
				if ( ! empty( $p['title'] ) ) {
					$html .= '<h3 class="tusb-principle__title">' . esc_html( $p['title'] ) . '</h3>';
				}
				if ( ! empty( $p['text'] ) ) {
					$html .= '<p class="tusb-principle__text">' . esc_html( $p['text'] ) . '</p>';
				}
				$html .= '</li>';
				$i++;
			}
			$html .= '</ol>';
		}
		$html .= '</div></div>';

		return $html;
	}

	/**
	 * Process section.
	 *
	 * @param array  $s Section.
	 * @param string $state State.
	 * @return string
	 */
	protected function section_process( $s, $state ) {
		$steps = tusb_arr( $s, 'steps', array() );
		$html  = '<div class="tusb-container">';
		$html .= $this->section_head( $s );
		if ( $steps ) {
			$html .= '<ol class="tusb-steps" data-tusb-repeater="process:steps">';
			$i = 1;
			foreach ( $steps as $step ) {
				$html .= '<li class="tusb-step">';
				$html .= '<span class="tusb-step__num">' . esc_html( sprintf( '%02d', $i ) ) . '</span>';
				$html .= '<div class="tusb-step__body">';
				if ( ! empty( $step['title'] ) ) {
					$html .= '<h3 class="tusb-step__title">' . esc_html( $step['title'] ) . '</h3>';
				}
				if ( ! empty( $step['duration'] ) ) {
					$html .= '<span class="tusb-step__meta">' . esc_html( $step['duration'] ) . '</span>';
				}
				if ( ! empty( $step['text'] ) ) {
					$html .= '<p class="tusb-step__text">' . esc_html( $step['text'] ) . '</p>';
				}
				$html .= '</div></li>';
				$i++;
			}
			$html .= '</ol>';
		}
		$html .= '</div>';
		return $html;
	}

	/**
	 * FAQ section.
	 *
	 * @param array  $s Section.
	 * @param string $state State.
	 * @return string
	 */
	protected function section_faq( $s, $state ) {
		$store  = tusb()->module( 'store' );
		$data   = $store ? $store->resolve( 'faq', $state ) : array( 'items' => array() );
		$items  = isset( $data['items'] ) ? array_values( array_filter( $data['items'], static function ( $i ) {
			return ! isset( $i['visible'] ) || $i['visible'];
		} ) ) : array();
		$limit  = isset( $s['limit'] ) ? (int) $s['limit'] : 8;
		$items  = $limit > 0 ? array_slice( $items, 0, $limit ) : $items;
		$open   = ! empty( $s['open_first'] );

		$html  = '<div class="tusb-container">';
		$html .= $this->section_head( $s );
		if ( $items ) {
			$html .= '<div class="tusb-faq" data-tusb-collection="faq">';
			$i = 0;
			foreach ( $items as $item ) {
				$item_id = isset( $item['id'] ) ? sanitize_key( $item['id'] ) : 'faq-' . $i;
				$is_open = ( $open && 0 === $i );
				$html   .= '<details class="tusb-faq__item" id="faq-' . esc_attr( $item_id ) . '"' . ( $is_open ? ' open' : '' ) . '>';
				$html   .= '<summary class="tusb-faq__q">' . esc_html( isset( $item['question'] ) ? $item['question'] : '' ) . '</summary>';
				$html   .= '<div class="tusb-faq__a">' . $this->safe_html( isset( $item['answer'] ) ? $item['answer'] : '' ) . '</div>';
				$html   .= '</details>';
				$i++;
			}
			$html .= '</div>';
		}
		$html .= '</div>';
		return $html;
	}

	/**
	 * CTA section.
	 *
	 * @param array  $s Section.
	 * @param string $state State.
	 * @return string
	 */
	protected function section_cta( $s, $state ) {
		$html  = '<div class="tusb-container">';
		$html .= '<div class="tusb-cta">';
		$html .= $this->heading( tusb_arr( $s, 'heading' ), 'h2', 'cta:heading', 'tusb-cta__heading' );
		$html .= $this->text( tusb_arr( $s, 'text' ), 'cta:text', 'tusb-cta__text' );
		$html .= $this->buttons( tusb_arr( $s, 'buttons', array() ), 'cta:buttons', 'tusb-cta__actions' );
		$html .= '</div></div>';
		return $html;
	}

	/**
	 * Contact section.
	 *
	 * @param array  $s Section.
	 * @param string $state State.
	 * @return string
	 */
	protected function section_contact( $s, $state ) {
		$store   = tusb()->module( 'store' );
		$contact = $store ? $store->resolve( 'contact', 'published' ) : array();

		$html  = '<div class="tusb-container">';
		$html .= $this->section_head( $s );
		$html .= '<div class="tusb-contact">';

		$html .= '<div class="tusb-contact__details">';
		$rows  = array(
			'email'    => array( __( 'Email', 'trustusbro-site-manager' ), 'mailto:' ),
			'phone'    => array( __( 'Phone', 'trustusbro-site-manager' ), 'tel:' ),
			'whatsapp' => array( __( 'WhatsApp', 'trustusbro-site-manager' ), 'tel:' ),
			'address'  => array( __( 'Address', 'trustusbro-site-manager' ), '' ),
			'hours'    => array( __( 'Hours', 'trustusbro-site-manager' ), '' ),
		);
		foreach ( $rows as $key => $config ) {
			$value = isset( $contact[ $key ] ) ? $contact[ $key ] : '';
			if ( '' === $value ) {
				continue;
			}
			$html .= '<div class="tusb-contact__row">';
			$html .= '<span class="tusb-contact__label">' . esc_html( $config[0] ) . '</span>';
			if ( $config[1] ) {
				$href  = $config[1] . ( 'tel:' === $config[1] ? preg_replace( '/[^0-9+]/', '', $value ) : $value );
				$html .= '<a class="tusb-contact__value" href="' . esc_url( $href ) . '">' . esc_html( $value ) . '</a>';
			} else {
				$html .= '<span class="tusb-contact__value">' . nl2br( esc_html( $value ) ) . '</span>';
			}
			$html .= '</div>';
		}
		$html .= '</div>';

		$show_form = ! isset( $s['show_form'] ) || ! empty( $s['show_form'] );
		if ( $show_form ) {
			$html .= '<div class="tusb-contact__form">';
			if ( ! empty( $s['form_heading'] ) ) {
				$html .= '<h3 class="tusb-contact__form-title">' . esc_html( $s['form_heading'] ) . '</h3>';
			}
			if ( ! empty( $s['form_shortcode'] ) ) {
				$html .= do_shortcode( wp_kses_post( $s['form_shortcode'] ) );
			} else {
				$html .= $this->fallback_form( isset( $contact['recipient'] ) ? $contact['recipient'] : '' );
			}
			$html .= '</div>';
		}

		$html .= '</div></div>';
		return $html;
	}

	/**
	 * A safe, no-dependency contact form used only when no form plugin shortcode
	 * is configured. It posts to admin-post.php with a nonce.
	 *
	 * @param string $recipient Recipient email.
	 * @return string
	 */
	protected function fallback_form( $recipient = '' ) {
		$sent = isset( $_GET['tusb_sent'] ) ? sanitize_key( wp_unslash( $_GET['tusb_sent'] ) ) : ''; // phpcs:ignore WordPress.Security.NonceVerification.Recommended
		$html = '';

		if ( 'ok' === $sent ) {
			$html .= '<p class="tusb-form__notice tusb-form__notice--ok" role="status">' . esc_html__( 'Thank you — your message has been sent.', 'trustusbro-site-manager' ) . '</p>';
		} elseif ( 'error' === $sent ) {
			$html .= '<p class="tusb-form__notice tusb-form__notice--error" role="alert">' . esc_html__( 'Sorry, the message could not be sent. Please email us directly.', 'trustusbro-site-manager' ) . '</p>';
		}

		$html .= '<form class="tusb-form" method="post" action="' . esc_url( admin_url( 'admin-post.php' ) ) . '">';
		$html .= '<input type="hidden" name="action" value="tusb_contact" />';
		$html .= '<input type="hidden" name="tusb_redirect" value="' . esc_url( $this->current_url() ) . '" />';
		$html .= wp_nonce_field( 'tusb_contact', 'tusb_contact_nonce', true, false );
		// Honeypot: bots fill it, humans never see it.
		$html .= '<p class="tusb-form__hp" aria-hidden="true"><label for="tusb-website">Website</label><input type="text" id="tusb-website" name="tusb_website" tabindex="-1" autocomplete="off" /></p>';

		$fields = array(
			'name'    => __( 'Your name', 'trustusbro-site-manager' ),
			'email'   => __( 'Email address', 'trustusbro-site-manager' ),
			'phone'   => __( 'Phone (optional)', 'trustusbro-site-manager' ),
		);
		foreach ( $fields as $name => $label ) {
			$type  = 'email' === $name ? 'email' : ( 'phone' === $name ? 'tel' : 'text' );
			$req   = 'phone' === $name ? '' : ' required';
			$html .= '<p class="tusb-form__field">';
			$html .= '<label for="tusb-' . esc_attr( $name ) . '">' . esc_html( $label ) . '</label>';
			$html .= '<input type="' . esc_attr( $type ) . '" id="tusb-' . esc_attr( $name ) . '" name="tusb_' . esc_attr( $name ) . '"' . $req . ' />';
			$html .= '</p>';
		}
		$html .= '<p class="tusb-form__field"><label for="tusb-message">' . esc_html__( 'Message', 'trustusbro-site-manager' ) . '</label>';
		$html .= '<textarea id="tusb-message" name="tusb_message" rows="5" required></textarea></p>';
		$html .= '<p class="tusb-form__submit"><button type="submit" class="tusb-btn tusb-btn--primary">' . esc_html__( 'Send message', 'trustusbro-site-manager' ) . '</button></p>';
		$html .= '</form>';

		return $html;
	}

	/**
	 * Current request URL, used for the post-submit redirect.
	 *
	 * @return string
	 */
	protected function current_url() {
		$path = isset( $_SERVER['REQUEST_URI'] ) ? esc_url_raw( wp_unslash( $_SERVER['REQUEST_URI'] ) ) : '/';
		return home_url( $path );
	}

	/**
	 * Text block section.
	 *
	 * @param array  $s Section.
	 * @param string $state State.
	 * @return string
	 */
	protected function section_text_block( $s, $state ) {
		$align = isset( $s['align'] ) && 'center' === $s['align'] ? ' tusb-textblock--center' : '';
		$html  = '<div class="tusb-container"><div class="tusb-textblock' . esc_attr( $align ) . '">';
		$html .= $this->section_head( $s );
		$html .= $this->safe_html( tusb_arr( $s, 'text' ) );
		if ( ! empty( $s['button']['label'] ) ) {
			$html .= '<div class="tusb-section__foot">' . $this->button( $s['button'], 'text_block:button' ) . '</div>';
		}
		$html .= '</div></div>';
		return $html;
	}

	/*
	 * ---------------------------------------------------------------------
	 * Cards
	 * ---------------------------------------------------------------------
	 */

	/**
	 * Service card.
	 *
	 * @param array $item Item.
	 * @return string
	 */
	protected function card_service( $item ) {
		$html  = '<article class="tusb-card tusb-card--service" data-tusb-item="' . esc_attr( isset( $item['id'] ) ? $item['id'] : '' ) . '">';
		$icon  = isset( $item['icon'] ) ? $item['icon'] : '';
		if ( $icon ) {
			$html .= '<span class="tusb-card__icon tusb-icon tusb-icon--' . esc_attr( $icon ) . '" aria-hidden="true">' . $this->icon_svg( $icon ) . '</span>';
		}
		$image = $this->image( tusb_arr( $item, 'image' ), 'medium_large', 'tusb-card__media' );
		if ( $image ) {
			$html .= $image;
		}
		if ( ! empty( $item['title'] ) ) {
			$html .= '<h3 class="tusb-card__title">' . esc_html( $item['title'] ) . '</h3>';
		}
		if ( ! empty( $item['summary'] ) ) {
			$html .= '<p class="tusb-card__text">' . esc_html( $item['summary'] ) . '</p>';
		}
		$features = tusb_arr( $item, 'features', array() );
		if ( $features ) {
			$html .= '<ul class="tusb-card__list">';
			foreach ( $features as $feature ) {
				if ( empty( $feature['text'] ) ) {
					continue;
				}
				$html .= '<li>' . esc_html( $feature['text'] ) . '</li>';
			}
			$html .= '</ul>';
		}
		if ( ! empty( $item['button']['label'] ) ) {
			$html .= '<div class="tusb-card__foot">' . $this->button( $item['button'], '', 'tusb-btn--link' ) . '</div>';
		}
		$html .= '</article>';
		return $html;
	}

	/**
	 * Industry card.
	 *
	 * @param array $item Item.
	 * @return string
	 */
	protected function card_industry( $item ) {
		$tag   = ! empty( $item['url'] ) ? 'a' : 'div';
		$href  = ! empty( $item['url'] ) ? ' href="' . esc_url( $item['url'] ) . '"' : '';
		$html  = '<' . $tag . ' class="tusb-card tusb-card--industry" data-tusb-item="' . esc_attr( isset( $item['id'] ) ? $item['id'] : '' ) . '"' . $href . '>';
		$image = $this->image( tusb_arr( $item, 'image' ), 'medium_large', 'tusb-card__media' );
		if ( $image ) {
			$html .= $image;
		}
		$html .= '<div class="tusb-card__body">';
		if ( ! empty( $item['title'] ) ) {
			$html .= '<h3 class="tusb-card__title">' . esc_html( $item['title'] ) . '</h3>';
		}
		if ( ! empty( $item['summary'] ) ) {
			$html .= '<p class="tusb-card__text">' . esc_html( $item['summary'] ) . '</p>';
		}
		$html .= '</div></' . $tag . '>';
		return $html;
	}

	/**
	 * Case study card.
	 *
	 * @param array $item Item.
	 * @return string
	 */
	protected function card_case_study( $item ) {
		$tag  = ! empty( $item['url'] ) ? 'a' : 'article';
		$href = ! empty( $item['url'] ) ? ' href="' . esc_url( $item['url'] ) . '"' : '';
		$html = '<' . $tag . ' class="tusb-card tusb-card--case" data-tusb-item="' . esc_attr( isset( $item['id'] ) ? $item['id'] : '' ) . '"' . $href . '>';
		$html .= $this->image( tusb_arr( $item, 'image' ), 'large', 'tusb-card__media tusb-card__media--wide' );
		$html .= '<div class="tusb-card__body">';
		if ( ! empty( $item['client'] ) ) {
			$html .= '<span class="tusb-card__kicker">' . esc_html( $item['client'] ) . '</span>';
		}
		if ( ! empty( $item['title'] ) ) {
			$html .= '<h3 class="tusb-card__title">' . esc_html( $item['title'] ) . '</h3>';
		}
		if ( ! empty( $item['summary'] ) ) {
			$html .= '<p class="tusb-card__text">' . esc_html( $item['summary'] ) . '</p>';
		}
		if ( ! empty( $item['result'] ) ) {
			$html .= '<p class="tusb-card__result">' . esc_html( $item['result'] ) . '</p>';
		}
		$tags = ! empty( $item['tags'] ) ? array_filter( array_map( 'trim', explode( ',', $item['tags'] ) ) ) : array();
		if ( $tags ) {
			$html .= '<ul class="tusb-tags">';
			foreach ( $tags as $tag_name ) {
				$html .= '<li>' . esc_html( $tag_name ) . '</li>';
			}
			$html .= '</ul>';
		}
		$html .= '</div></' . $tag . '>';
		return $html;
	}

	/**
	 * Testimonial card.
	 *
	 * @param array $item Item.
	 * @return string
	 */
	protected function card_testimonial( $item ) {
		$html  = '<figure class="tusb-card tusb-card--quote" data-tusb-item="' . esc_attr( isset( $item['id'] ) ? $item['id'] : '' ) . '">';
		$html .= '<blockquote class="tusb-card__quote">' . esc_html( isset( $item['quote'] ) ? $item['quote'] : '' ) . '</blockquote>';
		$html .= '<figcaption class="tusb-card__byline">';
		$html .= $this->image( tusb_arr( $item, 'avatar' ), 'thumbnail', 'tusb-card__avatar' );
		$html .= '<span class="tusb-card__byline-text">';
		if ( ! empty( $item['name'] ) ) {
			$html .= '<span class="tusb-card__name">' . esc_html( $item['name'] ) . '</span>';
		}
		if ( ! empty( $item['role'] ) ) {
			$html .= '<span class="tusb-card__role">' . esc_html( $item['role'] ) . '</span>';
		}
		$html .= '</span></figcaption></figure>';
		return $html;
	}

	/**
	 * Collection grid used by the shortcode.
	 *
	 * @param string $doc Collection key.
	 * @param int    $columns Columns.
	 * @param int    $limit Limit.
	 * @return string
	 */
	public function collection_grid( $doc, $columns = 3, $limit = 0 ) {
		$store = tusb()->module( 'store' );
		if ( ! $store ) {
			return '';
		}
		$data  = $store->resolve( $doc, 'published' );
		$items = isset( $data['items'] ) ? $data['items'] : array();
		$items = array_values( array_filter( $items, static function ( $item ) {
			return ! isset( $item['visible'] ) || $item['visible'];
		} ) );
		if ( $limit > 0 ) {
			$items = array_slice( $items, 0, $limit );
		}
		if ( ! $items ) {
			return '';
		}
		$columns = max( 1, min( 4, (int) $columns ) );
		$html    = '<div class="tusb-grid tusb-grid--' . esc_attr( $columns ) . '" data-tusb-collection="' . esc_attr( $doc ) . '">';
		foreach ( $items as $item ) {
			$html .= $this->{$this->card_method( $doc )}( $item );
		}
		$html .= '</div>';
		return $html;
	}

	/*
	 * ---------------------------------------------------------------------
	 * Header & footer
	 * ---------------------------------------------------------------------
	 */

	/**
	 * Render the editable header.
	 *
	 * @return void
	 */
	public function header() {
		if ( $this->header_rendered ) {
			return;
		}
		$this->header_rendered = true;
		$store  = tusb()->module( 'store' );
		$header = $store ? $store->resolve( 'header', 'published' ) : TUSB_Schema::defaults( 'header' );
		$logo   = $this->image( tusb_arr( $header, 'logo' ), 'medium', 'tusb-header__logo-img', false );
		$home   = ! empty( $header['logo_url'] ) ? $header['logo_url'] : home_url( '/' );
		$title  = ! empty( $header['logo_text'] ) ? $header['logo_text'] : get_bloginfo( 'name' );

		$classes = array( 'tusb-header' );
		if ( ! empty( $header['sticky'] ) ) {
			$classes[] = 'tusb-header--sticky';
		}
		if ( ! empty( $header['transparent'] ) ) {
			$classes[] = 'tusb-header--transparent';
		}

		echo '<header class="' . esc_attr( implode( ' ', $classes ) ) . '" role="banner">';
		echo '<div class="tusb-container tusb-header__inner">';

		echo '<a class="tusb-header__brand" href="' . esc_url( $home ) . '">';
		if ( $logo ) {
			echo $logo; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- escaped image markup.
		} else {
			echo '<span class="tusb-header__site-title">' . esc_html( $title ) . '</span>';
		}
		echo '</a>';

		echo '<nav class="tusb-nav" aria-label="' . esc_attr__( 'Primary navigation', 'trustusbro-site-manager' ) . '">';
		echo $this->nav_items( $header ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- escaped markup.
		echo '</nav>';

		if ( ! empty( $header['cta']['label'] ) ) {
			echo '<div class="tusb-header__cta">' . $this->button( $header['cta'], '', 'tusb-btn--primary' ) . '</div>'; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- escaped markup.
		}

		echo '<button class="tusb-menu-toggle" type="button" aria-expanded="false" aria-controls="tusb-mobile-nav">';
		echo '<span class="tusb-menu-toggle__label">' . esc_html( ! empty( $header['mobile_label'] ) ? $header['mobile_label'] : __( 'Menu', 'trustusbro-site-manager' ) ) . '</span>';
		echo '<span class="tusb-menu-toggle__bars" aria-hidden="true"><span></span><span></span></span>';
		echo '</button>';

		echo '</div>';

		echo '<div class="tusb-mobile-nav" id="tusb-mobile-nav" hidden>';
		echo '<div class="tusb-container">';
		echo $this->nav_items( $header, true ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- escaped markup.
		if ( ! empty( $header['cta']['label'] ) ) {
			echo '<div class="tusb-mobile-nav__cta">' . $this->button( $header['cta'], '', 'tusb-btn--primary' ) . '</div>'; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- escaped markup.
		}
		echo '</div></div>';

		echo '</header>';
	}

	/**
	 * Navigation markup, from a WordPress menu or the stored items.
	 *
	 * @param array $header Header data.
	 * @param bool  $mobile Mobile variant.
	 * @return string
	 */
	protected function nav_items( $header, $mobile = false ) {
		$list_class = $mobile ? 'tusb-nav__list tusb-nav__list--mobile' : 'tusb-nav__list';

		if ( ! empty( $header['use_wp_menu'] ) ) {
			$menu_name = TUSB_Design::token( 'header_menu', '' );
			if ( $menu_name ) {
				$items = wp_get_nav_menu_items( $menu_name );
				if ( $items ) {
					$html = '<ul class="' . esc_attr( $list_class ) . '">';
					foreach ( $items as $item ) {
						if ( (int) $item->menu_item_parent ) {
							continue; // Sub-items are handled below for the desktop menu.
						}
						$html .= '<li class="tusb-nav__item"><a class="tusb-nav__link" href="' . esc_url( $item->url ) . '">' . esc_html( $item->title ) . '</a></li>';
					}
					$html .= '</ul>';
					return $html;
				}
			}
		}

		$items = tusb_arr( $header, 'menu_items', array() );
		if ( ! $items ) {
			return '';
		}

		$html = '<ul class="' . esc_attr( $list_class ) . '">';
		foreach ( $items as $item ) {
			if ( empty( $item['label'] ) ) {
				continue;
			}
			$children = tusb_arr( $item, 'children', array() );
			$has_kids = ! $mobile && $children;
			$html    .= '<li class="tusb-nav__item' . ( $has_kids ? ' tusb-nav__item--has-children' : '' ) . '">';
			$html    .= '<a class="tusb-nav__link" href="' . esc_url( ! empty( $item['url'] ) ? $item['url'] : '#' ) . '">' . esc_html( $item['label'] ) . '</a>';
			if ( $has_kids ) {
				$html .= '<ul class="tusb-nav__submenu">';
				foreach ( $children as $child ) {
					if ( empty( $child['label'] ) ) {
						continue;
					}
					$html .= '<li class="tusb-nav__subitem"><a class="tusb-nav__link" href="' . esc_url( ! empty( $child['url'] ) ? $child['url'] : '#' ) . '">' . esc_html( $child['label'] ) . '</a></li>';
				}
				$html .= '</ul>';
			}
			$html .= '</li>';
		}
		$html .= '</ul>';
		return $html;
	}

	/**
	 * Render the editable footer with the approved four-column structure.
	 *
	 * @return void
	 */
	public function footer() {
		if ( $this->footer_rendered ) {
			return;
		}
		$this->footer_rendered = true;
		$store  = tusb()->module( 'store' );
		$footer = $store ? $store->resolve( 'footer', 'published' ) : TUSB_Schema::defaults( 'footer' );

		echo '<footer class="tusb-footer" role="contentinfo">';
		echo '<div class="tusb-container">';
		echo '<div class="tusb-footer__grid">';

		// Column 1 — brand.
		echo '<div class="tusb-footer__col tusb-footer__col--brand">';
		$logo = $this->image( tusb_arr( $footer, 'logo' ), 'medium', 'tusb-footer__logo', false );
		if ( $logo ) {
			echo $logo; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- escaped image markup.
		} elseif ( ! empty( $footer['tagline'] ) ) {
			echo '<span class="tusb-footer__wordmark">' . esc_html( $footer['tagline'] ) . '</span>';
		}
		if ( ! empty( $footer['tagline'] ) && $logo ) {
			echo '<span class="tusb-footer__wordmark">' . esc_html( $footer['tagline'] ) . '</span>';
		}
		if ( ! empty( $footer['description'] ) ) {
			echo '<p class="tusb-footer__text">' . esc_html( $footer['description'] ) . '</p>';
		}
		$social = tusb_arr( $footer, 'social', array() );
		if ( $social ) {
			echo '<ul class="tusb-footer__social">';
			foreach ( $social as $link ) {
				if ( empty( $link['url'] ) ) {
					continue;
				}
				$network = isset( $link['network'] ) ? $link['network'] : 'other';
				$label   = ! empty( $link['label'] ) ? $link['label'] : ucfirst( $network );
				echo '<li><a href="' . esc_url( $link['url'] ) . '" rel="noopener noreferrer" target="_blank" aria-label="' . esc_attr( $label ) . '">' . esc_html( $label ) . '</a></li>';
			}
			echo '</ul>';
		}
		echo '</div>';

		// Columns 2-4 — links.
		$columns = tusb_arr( $footer, 'columns', array() );
		foreach ( $columns as $column ) {
			if ( empty( $column['title'] ) && empty( $column['links'] ) ) {
				continue;
			}
			echo '<div class="tusb-footer__col">';
			if ( ! empty( $column['title'] ) ) {
				echo '<h2 class="tusb-footer__heading">' . esc_html( $column['title'] ) . '</h2>';
			}
			$links = tusb_arr( $column, 'links', array() );
			if ( $links ) {
				echo '<ul class="tusb-footer__links">';
				foreach ( $links as $link ) {
					if ( empty( $link['label'] ) ) {
						continue;
					}
					echo '<li><a href="' . esc_url( ! empty( $link['url'] ) ? $link['url'] : '#' ) . '">' . esc_html( $link['label'] ) . '</a></li>';
				}
				echo '</ul>';
			}
			echo '</div>';
		}

		echo '</div>';

		echo '<div class="tusb-footer__bar">';
		echo '<div class="tusb-footer__bar-inner">';
		$copyright = ! empty( $footer['copyright'] ) ? $footer['copyright'] : '© {year} {site}';
		$copyright = str_replace(
			array( '{year}', '{site}' ),
			array( gmdate( 'Y' ), get_bloginfo( 'name' ) ),
			$copyright
		);
		echo '<p class="tusb-footer__copy">' . esc_html( $copyright ) . '</p>';
		$legal = tusb_arr( $footer, 'legal_links', array() );
		if ( $legal ) {
			echo '<ul class="tusb-footer__legal">';
			foreach ( $legal as $link ) {
				if ( empty( $link['label'] ) ) {
					continue;
				}
				echo '<li><a href="' . esc_url( ! empty( $link['url'] ) ? $link['url'] : '#' ) . '">' . esc_html( $link['label'] ) . '</a></li>';
			}
			echo '</ul>';
		}
		echo '</div></div>';

		echo '</div></footer>';
	}

	/*
	 * ---------------------------------------------------------------------
	 * Preview route
	 * ---------------------------------------------------------------------
	 */

	/**
	 * Serve a standalone preview of a document for signed-in editors.
	 *
	 * @return void
	 */
	public function handle_preview() {
		$doc_key = tusb_preview_doc();
		if ( ! $doc_key ) {
			return;
		}
		// Render through our own template so previews never depend on the theme.
		$GLOBALS['tusb_preview_doc_key'] = $doc_key;
		nocache_headers();
	}

	/**
	 * Swap in the preview template when previewing.
	 *
	 * @param string $template Template path.
	 * @return string
	 */
	public function preview_template( $template ) {
		$doc_key = tusb_preview_doc();
		if ( ! $doc_key ) {
			return $template;
		}
		$preview = TUSB_DIR . 'templates/preview.php';
		return file_exists( $preview ) ? $preview : $template;
	}

	/**
	 * Preview document title.
	 *
	 * @param string $title Title.
	 * @return string
	 */
	public function preview_title( $title ) {
		$doc_key = tusb_preview_doc();
		if ( ! $doc_key ) {
			return $title;
		}
		return sprintf(
			/* translators: %s: document label. */
			__( 'Preview: %s', 'trustusbro-site-manager' ),
			tusb_doc_label( $doc_key )
		);
	}

	/**
	 * Render an entire document for the preview shell (header + body + footer).
	 *
	 * @param string $doc_key Document key.
	 * @return string
	 */
	public function render_preview_body( $doc_key ) {
		$doc = TUSB_Schema::doc( $doc_key );
		if ( ! $doc ) {
			return '<p class="tusb-empty">' . esc_html__( 'This document does not exist.', 'trustusbro-site-manager' ) . '</p>';
		}

		$type = tusb_arr( $doc, 'type' );

		ob_start();
		if ( 'sections' === $type ) {
			echo $this->render_page( $doc_key, 'draft' ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- escaped markup.
		} elseif ( 'collection' === $type ) {
			$columns = 'testimonials' === $doc_key ? 2 : 3;
			echo '<div class="tusb-container tusb-preview-collection"><h1 class="tusb-h1">' . esc_html( tusb_doc_label( $doc_key ) ) . '</h1>';
			echo $this->collection_grid( $doc_key, $columns, 0 ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- escaped markup.
			echo '</div>';
		} else {
			$store = tusb()->module( 'store' );
			$data  = $store ? $store->resolve( $doc_key, 'draft' ) : array();
			echo '<div class="tusb-container tusb-preview-record">';
			echo '<h1 class="tusb-h1">' . esc_html( tusb_doc_label( $doc_key ) ) . '</h1>';
			echo '<table class="tusb-preview-table"><tbody>';
			foreach ( (array) $data as $key => $value ) {
				echo '<tr><th scope="row">' . esc_html( ucwords( str_replace( '_', ' ', (string) $key ) ) ) . '</th><td>';
				echo $this->preview_value( $value ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- escaped markup.
				echo '</td></tr>';
			}
			echo '</tbody></table></div>';
		}
		return ob_get_clean();
	}

	/**
	 * Format a record value for the preview table.
	 *
	 * @param mixed $value Value.
	 * @return string
	 */
	protected function preview_value( $value ) {
		if ( is_bool( $value ) ) {
			return $value ? esc_html__( 'Yes', 'trustusbro-site-manager' ) : esc_html__( 'No', 'trustusbro-site-manager' );
		}
		if ( is_int( $value ) && $value > 0 && 'attachment' === get_post_type( $value ) ) {
			$src = wp_get_attachment_image_url( $value, 'medium' );
			return $src ? '<img src="' . esc_url( $src ) . '" alt="" style="max-width:160px;height:auto" />' : '';
		}
		if ( is_array( $value ) ) {
			$out = '<ul class="tusb-preview-list">';
			foreach ( $value as $row ) {
				if ( is_array( $row ) ) {
					$parts = array();
					foreach ( $row as $k => $v ) {
						if ( is_scalar( $v ) && '' !== $v && 'id' !== $k ) {
							$parts[] = esc_html( $v );
						}
					}
					$out .= '<li>' . implode( ' — ', $parts ) . '</li>';
				} elseif ( is_scalar( $row ) && '' !== $row ) {
					$out .= '<li>' . esc_html( (string) $row ) . '</li>';
				}
			}
			$out .= '</ul>';
			return $out;
		}
		if ( is_scalar( $value ) ) {
			return '' === (string) $value ? '<span class="tusb-dim">—</span>' : esc_html( (string) $value );
		}
		return '';
	}

	/*
	 * ---------------------------------------------------------------------
	 * HTML helpers
	 * ---------------------------------------------------------------------
	 */

	/**
	 * Section head (eyebrow, heading, intro text).
	 *
	 * @param array $s Section.
	 * @return string
	 */
	protected function section_head( $s ) {
		$html = '<div class="tusb-section__head">';
		$html .= $this->eyebrow( tusb_arr( $s, 'eyebrow' ) );
		$html .= $this->heading( tusb_arr( $s, 'heading' ), 'h2' );
		$html .= $this->text( tusb_arr( $s, 'text' ) );
		$html .= '</div>';
		return $html;
	}

	/**
	 * Eyebrow label.
	 *
	 * @param string $value Value.
	 * @param string $field Field path for inline editing.
	 * @return string
	 */
	protected function eyebrow( $value, $field = '' ) {
		if ( '' === trim( (string) $value ) ) {
			return '';
		}
		return '<p class="tusb-eyebrow"' . $this->field_attr( $field ) . '>' . esc_html( $value ) . '</p>';
	}

	/**
	 * Heading. Supports *highlight* markers which map to the accent colour
	 * without changing the surrounding typography.
	 *
	 * @param string $value Value.
	 * @param string $tag Tag.
	 * @param string $field Field path.
	 * @param string $class Extra class.
	 * @return string
	 */
	protected function heading( $value, $tag = 'h2', $field = '', $class = '' ) {
		$value = trim( (string) $value );
		if ( '' === $value ) {
			return '';
		}
		$allowed_tag = in_array( $tag, array( 'h1', 'h2', 'h3' ), true ) ? $tag : 'h2';
		$text        = esc_html( $value );
		// Only *emphasis* is interpreted; everything else is plain text.
		$text = preg_replace( '/\*(.+?)\*/s', '<span class="tusb-accent">$1</span>', $text );

		return sprintf(
			'<%1$s class="tusb-heading %2$s"%3$s>%4$s</%1$s>',
			$allowed_tag,
			esc_attr( $class ),
			$this->field_attr( $field ),
			$text
		);
	}

	/**
	 * Paragraph text.
	 *
	 * @param string $value Value.
	 * @param string $field Field.
	 * @param string $class Class.
	 * @return string
	 */
	protected function text( $value, $field = '', $class = '' ) {
		$value = trim( (string) $value );
		if ( '' === $value ) {
			return '';
		}
		return '<p class="tusb-text ' . esc_attr( $class ) . '"' . $this->field_attr( $field ) . '>' . nl2br( esc_html( $value ) ) . '</p>';
	}

	/**
	 * Rich text output (already sanitised on save; re-filtered defensively).
	 *
	 * @param string $value Value.
	 * @return string
	 */
	protected function safe_html( $value ) {
		$value = (string) $value;
		if ( '' === trim( $value ) ) {
			return '';
		}
		$html = wp_kses( $value, TUSB_Sanitizer::kses_allowed() );
		return wpautop( $html );
	}

	/**
	 * Build a data-tusb-field attribute.
	 *
	 * @param string $field Field path.
	 * @return string
	 */
	protected function field_attr( $field ) {
		return $field ? ' data-tusb-field="' . esc_attr( $field ) . '"' : '';
	}

	/**
	 * Buttons from a repeater.
	 *
	 * @param array  $buttons Buttons.
	 * @param string $field Field path.
	 * @param string $class Wrapper class.
	 * @return string
	 */
	protected function buttons( $buttons, $field = '', $class = '' ) {
		if ( empty( $buttons ) || ! is_array( $buttons ) ) {
			return '';
		}
		$html = '<div class="tusb-actions ' . esc_attr( $class ) . '"' . $this->field_attr( $field ) . '>';
		foreach ( $buttons as $button ) {
			$html .= $this->button( $button, '' );
		}
		$html .= '</div>';
		return $html;
	}

	/**
	 * One button.
	 *
	 * @param array  $button Button data.
	 * @param string $field Field path.
	 * @param string $class Extra class.
	 * @return string
	 */
	protected function button( $button, $field = '', $class = '' ) {
		$label = isset( $button['label'] ) ? trim( (string) $button['label'] ) : '';
		if ( '' === $label ) {
			return '';
		}
		$url   = isset( $button['url'] ) ? $button['url'] : '';
		$style = isset( $button['style'] ) ? $button['style'] : 'primary';
		$style = in_array( $style, array( 'primary', 'ghost', 'text' ), true ) ? $style : 'primary';

		return sprintf(
			'<a class="tusb-btn tusb-btn--%1$s %2$s" href="%3$s"%4$s>%5$s</a>',
			esc_attr( $style ),
			esc_attr( $class ),
			esc_url( $url ? $url : '#' ),
			$this->field_attr( $field ),
			esc_html( $label )
		);
	}

	/**
	 * Responsive image from an attachment ID.
	 *
	 * @param mixed  $attachment_id Attachment ID.
	 * @param string $size Size.
	 * @param string $class Class.
	 * @param bool   $figure Wrap in figure.
	 * @return string
	 */
	protected function image( $attachment_id, $size = 'large', $class = '', $figure = true ) {
		$id = (int) $attachment_id;
		if ( ! $id || 'attachment' !== get_post_type( $id ) ) {
			return '';
		}
		$html = wp_get_attachment_image(
			$id,
			$size,
			false,
			array(
				'class'    => $class,
				'loading'  => 'lazy',
				'decoding' => 'async',
			)
		);
		if ( ! $html ) {
			return '';
		}
		if ( ! $figure ) {
			return $html;
		}
		return '<figure class="tusb-media">' . $html . '</figure>';
	}

	/**
	 * Inline SVG icons. Kept in code so no icon library is needed, and drawn with
	 * currentColor so they inherit the palette.
	 *
	 * @param string $name Icon name.
	 * @return string
	 */
	protected function icon_svg( $name ) {
		$paths = array(
			'design'    => '<path d="M12 3l2.6 5.6 6.1.8-4.4 4.3 1.1 6-5.4-3-5.4 3 1.1-6L3.3 9.4l6.1-.8z"/>',
			'code'      => '<path d="M8 6l-5 6 5 6M16 6l5 6-5 6"/>',
			'search'    => '<circle cx="11" cy="11" r="7"/><path d="M16.5 16.5L21 21"/>',
			'chart'     => '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
			'sparkle'   => '<path d="M12 3v6M12 15v6M3 12h6M15 12h6M6 6l3 3M15 15l3 3M18 6l-3 3M9 15l-3 3"/>',
			'settings'  => '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1"/>',
			'camera'    => '<rect x="3" y="7" width="18" height="13" rx="1"/><circle cx="12" cy="13" r="4"/><path d="M8 7l2-3h4l2 3"/>',
			'briefcase' => '<rect x="3" y="7" width="18" height="13" rx="1"/><path d="M9 7V5h6v2"/>',
		);
		$path = isset( $paths[ $name ] ) ? $paths[ $name ] : $paths['sparkle'];
		return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' . $path . '</svg>';
	}

	/**
	 * Are we rendering for an editor (so empty states should be shown)?
	 *
	 * @return bool
	 */
	protected function is_editor_context() {
		return is_user_logged_in() && current_user_can( 'edit_posts' );
	}
}
