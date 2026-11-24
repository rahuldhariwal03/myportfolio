<?php
/**
 * Content schema.
 *
 * Single source of truth for what is editable: field definitions drive the
 * dashboard forms, sanitisation, validation, defaults and the renderer.
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

/**
 * Schema registry.
 */
class TUSB_Schema {

	/**
	 * Cached schema.
	 *
	 * @var array|null
	 */
	private static $schema = null;

	/**
	 * Field types that are safe to persist.
	 *
	 * @var string[]
	 */
	const TYPES = array(
		'text',
		'textarea',
		'html',
		'url',
		'email',
		'tel',
		'image',
		'select',
		'toggle',
		'number',
		'color',
		'css_length',
		'font',
		'repeater',
		'group',
		'hidden',
	);

	/**
	 * Get the whole schema, filterable so themes/agencies can extend it.
	 *
	 * @return array
	 */
	public static function all() {
		if ( null === self::$schema ) {
			self::$schema = self::build();
		}
		/**
		 * Filter the Site Manager content schema.
		 *
		 * @param array $schema Schema definition.
		 */
		return apply_filters( 'tusb_schema', self::$schema );
	}

	/**
	 * Get a single document definition.
	 *
	 * @param string $doc_key Document key.
	 * @return array
	 */
	public static function doc( $doc_key ) {
		$schema = self::all();
		return isset( $schema[ $doc_key ] ) ? $schema[ $doc_key ] : array();
	}

	/**
	 * Get the section definition inside a sections document.
	 *
	 * @param string $doc_key Document key.
	 * @param string $section_type Section type.
	 * @return array
	 */
	public static function section( $doc_key, $section_type ) {
		$doc = self::doc( $doc_key );
		if ( 'sections' !== tusb_arr( $doc, 'type' ) ) {
			return array();
		}
		$sections = tusb_arr( $doc, 'sections', array() );
		return isset( $sections[ $section_type ] ) ? $sections[ $section_type ] : array();
	}

	/**
	 * Return default record for a document, built from field defaults.
	 *
	 * @param string $doc_key Document key.
	 * @return array
	 */
	public static function defaults( $doc_key ) {
		$doc = self::doc( $doc_key );
		if ( ! $doc ) {
			return array();
		}

		switch ( tusb_arr( $doc, 'type' ) ) {
			case 'sections':
				$sections = array();
				foreach ( $doc['sections'] as $type => $section ) {
					$sections[] = array_merge(
						array(
							'id'      => 'default-' . $type,
							'type'    => $type,
							'enabled' => true,
						),
						self::field_defaults( isset( $section['fields'] ) ? $section['fields'] : array() )
					);
				}
				return array( 'sections' => $sections );

			case 'collection':
				return array( 'items' => array() );

			case 'record':
			default:
				return self::field_defaults( isset( $doc['fields'] ) ? $doc['fields'] : array() );
		}
	}

	/**
	 * Extract defaults from a field map.
	 *
	 * @param array $fields Field map.
	 * @return array
	 */
	public static function field_defaults( $fields ) {
		$out = array();
		foreach ( (array) $fields as $key => $field ) {
			$out[ $key ] = self::field_default( $field );
		}
		return $out;
	}

	/**
	 * Resolve the default for one field definition.
	 *
	 * @param array $field Field definition.
	 * @return mixed
	 */
	public static function field_default( $field ) {
		$type = tusb_arr( $field, 'type', 'text' );

		if ( isset( $field['default'] ) ) {
			return $field['default'];
		}

		switch ( $type ) {
			case 'repeater':
				return array();
			case 'group':
				return self::field_defaults( tusb_arr( $field, 'fields', array() ) );
			case 'toggle':
				return false;
			case 'number':
				return 0;
			case 'image':
				return 0;
			default:
				return '';
		}
	}

	/**
	 * Build the schema.
	 *
	 * @return array
	 */
	private static function build() {
		$link_fields = array(
			'label' => array(
				'type'  => 'text',
				'label' => __( 'Button label', 'trustusbro-site-manager' ),
				'help'  => __( 'Short text shown on the button. Leave blank to hide the button.', 'trustusbro-site-manager' ),
			),
			'url'   => array(
				'type'  => 'url',
				'label' => __( 'Button link', 'trustusbro-site-manager' ),
			),
			'style' => array(
				'type'    => 'select',
				'label'   => __( 'Button style', 'trustusbro-site-manager' ),
				'options' => array(
					'primary' => __( 'Primary (filled)', 'trustusbro-site-manager' ),
					'ghost'   => __( 'Secondary (outline)', 'trustusbro-site-manager' ),
					'text'    => __( 'Link', 'trustusbro-site-manager' ),
				),
				'default' => 'primary',
			),
		);

		$eyebrow_field = array(
			'type'  => 'text',
			'label' => __( 'Small label above heading', 'trustusbro-site-manager' ),
		);

		$schema = array();

		/*
		 * ---------------------------------------------------------------
		 * Homepage (sections)
		 * ---------------------------------------------------------------
		 */
		$schema['home'] = array(
			'label'    => __( 'Homepage', 'trustusbro-site-manager' ),
			'type'     => 'sections',
			'icon'     => 'dashicons-admin-home',
			'sections' => array(
				'hero'         => array(
					'label'        => __( 'Hero', 'trustusbro-site-manager' ),
					'icon'         => 'dashicons-superhero',
					'description'  => __( 'First screen: headline, supporting text, buttons and image.', 'trustusbro-site-manager' ),
					'supports'     => array( 'buttons', 'image' ),
					'fields'       => array(
						'eyebrow'         => $eyebrow_field,
						'heading'         => array(
							'type'     => 'textarea',
							'label'    => __( 'Headline', 'trustusbro-site-manager' ),
							'help'     => __( 'You can use *asterisks* around a word to highlight it.', 'trustusbro-site-manager' ),
							'default'  => __( 'Your headline goes here', 'trustusbro-site-manager' ),
							'required' => true,
						),
						'text'            => array(
							'type'    => 'textarea',
							'label'   => __( 'Supporting text', 'trustusbro-site-manager' ),
							'default' => __( 'Replace this placeholder with a short sentence describing what you do and who you help.', 'trustusbro-site-manager' ),
						),
						'buttons'         => array(
							'type'   => 'repeater',
							'label'  => __( 'Buttons', 'trustusbro-site-manager' ),
							'fields' => $link_fields,
							'max'    => 3,
						),
						'image'           => array(
							'type'  => 'image',
							'label' => __( 'Hero image', 'trustusbro-site-manager' ),
						),
						'image_position'  => array(
							'type'    => 'select',
							'label'   => __( 'Image position', 'trustusbro-site-manager' ),
							'options' => array(
								'right' => __( 'Right of text', 'trustusbro-site-manager' ),
								'left'  => __( 'Left of text', 'trustusbro-site-manager' ),
								'above' => __( 'Above text', 'trustusbro-site-manager' ),
								'none'  => __( 'No image', 'trustusbro-site-manager' ),
							),
							'default' => 'right',
						),
						'note'            => array(
							'type'  => 'text',
							'label' => __( 'Availability note', 'trustusbro-site-manager' ),
							'help'  => __( 'Optional line under the buttons, e.g. a status or promise.', 'trustusbro-site-manager' ),
						),
					),
				),
				'services'     => array(
					'label'       => __( 'Services', 'trustusbro-site-manager' ),
					'icon'        => 'dashicons-screenoptions',
					'description' => __( 'Cards pulled from the Services Manager. Reorder cards there.', 'trustusbro-site-manager' ),
					'source'      => 'services',
					'fields'      => array(
						'eyebrow'    => $eyebrow_field,
						'heading'    => array(
							'type'    => 'text',
							'label'   => __( 'Heading', 'trustusbro-site-manager' ),
							'default' => __( 'What we do', 'trustusbro-site-manager' ),
						),
						'text'       => array(
							'type'  => 'textarea',
							'label' => __( 'Intro text', 'trustusbro-site-manager' ),
						),
						'columns'    => array(
							'type'    => 'select',
							'label'   => __( 'Columns', 'trustusbro-site-manager' ),
							'options' => array(
								'2' => __( 'Two', 'trustusbro-site-manager' ),
								'3' => __( 'Three', 'trustusbro-site-manager' ),
								'4' => __( 'Four', 'trustusbro-site-manager' ),
							),
							'default' => '3',
						),
						'limit'      => array(
							'type'    => 'number',
							'label'   => __( 'Maximum cards', 'trustusbro-site-manager' ),
							'default' => 6,
							'min'     => 1,
							'max'     => 24,
						),
						'button'     => array(
							'type'   => 'group',
							'label'  => __( 'Section button', 'trustusbro-site-manager' ),
							'fields' => $link_fields,
						),
					),
				),
				'industries'   => array(
					'label'       => __( 'Industries', 'trustusbro-site-manager' ),
					'icon'        => 'dashicons-building',
					'description' => __( 'Industry cards pulled from the Industries Manager.', 'trustusbro-site-manager' ),
					'source'      => 'industries',
					'fields'      => array(
						'eyebrow' => $eyebrow_field,
						'heading' => array(
							'type'    => 'text',
							'label'   => __( 'Heading', 'trustusbro-site-manager' ),
							'default' => __( 'Who we work with', 'trustusbro-site-manager' ),
						),
						'text'    => array(
							'type'  => 'textarea',
							'label' => __( 'Intro text', 'trustusbro-site-manager' ),
						),
						'columns' => array(
							'type'    => 'select',
							'label'   => __( 'Columns', 'trustusbro-site-manager' ),
							'options' => array(
								'2' => __( 'Two', 'trustusbro-site-manager' ),
								'3' => __( 'Three', 'trustusbro-site-manager' ),
								'4' => __( 'Four', 'trustusbro-site-manager' ),
							),
							'default' => '3',
						),
						'limit'   => array(
							'type'    => 'number',
							'label'   => __( 'Maximum cards', 'trustusbro-site-manager' ),
							'default' => 9,
							'min'     => 1,
							'max'     => 24,
						),
					),
				),
				'philosophy'   => array(
					'label'       => __( 'Agency philosophy', 'trustusbro-site-manager' ),
					'icon'        => 'dashicons-lightbulb',
					'description' => __( 'A statement section with a list of principles.', 'trustusbro-site-manager' ),
					'supports'    => array( 'image' ),
					'fields'      => array(
						'eyebrow'    => $eyebrow_field,
						'heading'    => array(
							'type'    => 'text',
							'label'   => __( 'Heading', 'trustusbro-site-manager' ),
							'default' => __( 'How we think', 'trustusbro-site-manager' ),
						),
						'text'       => array(
							'type'  => 'textarea',
							'label' => __( 'Statement', 'trustusbro-site-manager' ),
						),
						'image'      => array(
							'type'  => 'image',
							'label' => __( 'Image', 'trustusbro-site-manager' ),
						),
						'principles' => array(
							'type'   => 'repeater',
							'label'  => __( 'Principles', 'trustusbro-site-manager' ),
							'fields' => array(
								'title' => array(
									'type'  => 'text',
									'label' => __( 'Title', 'trustusbro-site-manager' ),
								),
								'text'  => array(
									'type'  => 'textarea',
									'label' => __( 'Description', 'trustusbro-site-manager' ),
								),
							),
							'max'    => 8,
						),
					),
				),
				'process'      => array(
					'label'       => __( 'Process', 'trustusbro-site-manager' ),
					'icon'        => 'dashicons-editor-ol',
					'description' => __( 'Numbered steps.', 'trustusbro-site-manager' ),
					'fields'      => array(
						'eyebrow' => $eyebrow_field,
						'heading' => array(
							'type'    => 'text',
							'label'   => __( 'Heading', 'trustusbro-site-manager' ),
							'default' => __( 'How we work', 'trustusbro-site-manager' ),
						),
						'text'    => array(
							'type'  => 'textarea',
							'label' => __( 'Intro text', 'trustusbro-site-manager' ),
						),
						'steps'   => array(
							'type'   => 'repeater',
							'label'  => __( 'Steps', 'trustusbro-site-manager' ),
							'fields' => array(
								'title'       => array(
									'type'  => 'text',
									'label' => __( 'Step title', 'trustusbro-site-manager' ),
								),
								'text'        => array(
									'type'  => 'textarea',
									'label' => __( 'Step description', 'trustusbro-site-manager' ),
								),
								'duration'    => array(
									'type'  => 'text',
									'label' => __( 'Duration / label', 'trustusbro-site-manager' ),
								),
							),
							'max'    => 10,
						),
					),
				),
				'case_studies' => array(
					'label'       => __( 'Case studies', 'trustusbro-site-manager' ),
					'icon'        => 'dashicons-portfolio',
					'description' => __( 'Case study cards from the Case Studies Manager.', 'trustusbro-site-manager' ),
					'source'      => 'case_studies',
					'fields'      => array(
						'eyebrow' => $eyebrow_field,
						'heading' => array(
							'type'    => 'text',
							'label'   => __( 'Heading', 'trustusbro-site-manager' ),
							'default' => __( 'Selected work', 'trustusbro-site-manager' ),
						),
						'text'    => array(
							'type'  => 'textarea',
							'label' => __( 'Intro text', 'trustusbro-site-manager' ),
						),
						'columns' => array(
							'type'    => 'select',
							'label'   => __( 'Columns', 'trustusbro-site-manager' ),
							'options' => array(
								'2' => __( 'Two', 'trustusbro-site-manager' ),
								'3' => __( 'Three', 'trustusbro-site-manager' ),
							),
							'default' => '2',
						),
						'limit'   => array(
							'type'    => 'number',
							'label'   => __( 'Maximum cards', 'trustusbro-site-manager' ),
							'default' => 4,
							'min'     => 1,
							'max'     => 12,
						),
					),
				),
				'testimonials' => array(
					'label'       => __( 'Testimonials', 'trustusbro-site-manager' ),
					'icon'        => 'dashicons-format-quote',
					'description' => __( 'Client quotes from the Testimonials Manager.', 'trustusbro-site-manager' ),
					'source'      => 'testimonials',
					'fields'      => array(
						'eyebrow' => $eyebrow_field,
						'heading' => array(
							'type'    => 'text',
							'label'   => __( 'Heading', 'trustusbro-site-manager' ),
							'default' => __( 'What clients say', 'trustusbro-site-manager' ),
						),
						'text'    => array(
							'type'  => 'textarea',
							'label' => __( 'Intro text', 'trustusbro-site-manager' ),
						),
						'columns' => array(
							'type'    => 'select',
							'label'   => __( 'Columns', 'trustusbro-site-manager' ),
							'options' => array(
								'1' => __( 'One', 'trustusbro-site-manager' ),
								'2' => __( 'Two', 'trustusbro-site-manager' ),
								'3' => __( 'Three', 'trustusbro-site-manager' ),
							),
							'default' => '2',
						),
						'limit'   => array(
							'type'    => 'number',
							'label'   => __( 'Maximum quotes', 'trustusbro-site-manager' ),
							'default' => 4,
							'min'     => 1,
							'max'     => 12,
						),
					),
				),
				'faq'          => array(
					'label'       => __( 'FAQ', 'trustusbro-site-manager' ),
					'icon'        => 'dashicons-editor-help',
					'description' => __( 'Questions from the FAQ Manager.', 'trustusbro-site-manager' ),
					'source'      => 'faq',
					'fields'      => array(
						'eyebrow' => $eyebrow_field,
						'heading' => array(
							'type'    => 'text',
							'label'   => __( 'Heading', 'trustusbro-site-manager' ),
							'default' => __( 'Frequently asked questions', 'trustusbro-site-manager' ),
						),
						'text'    => array(
							'type'  => 'textarea',
							'label' => __( 'Intro text', 'trustusbro-site-manager' ),
						),
						'limit'   => array(
							'type'    => 'number',
							'label'   => __( 'Maximum questions', 'trustusbro-site-manager' ),
							'default' => 8,
							'min'     => 1,
							'max'     => 30,
						),
						'open_first' => array(
							'type'    => 'toggle',
							'label'   => __( 'Open the first question by default', 'trustusbro-site-manager' ),
							'default' => false,
						),
					),
				),
				'cta'          => array(
					'label'       => __( 'Call to action', 'trustusbro-site-manager' ),
					'icon'        => 'dashicons-megaphone',
					'description' => __( 'Centred prompt with buttons.', 'trustusbro-site-manager' ),
					'fields'      => array(
						'heading' => array(
							'type'    => 'text',
							'label'   => __( 'Heading', 'trustusbro-site-manager' ),
							'default' => __( 'Ready to start?', 'trustusbro-site-manager' ),
						),
						'text'    => array(
							'type'  => 'textarea',
							'label' => __( 'Text', 'trustusbro-site-manager' ),
						),
						'buttons' => array(
							'type'   => 'repeater',
							'label'  => __( 'Buttons', 'trustusbro-site-manager' ),
							'fields' => $link_fields,
							'max'    => 2,
						),
					),
				),
				'contact'      => array(
					'label'       => __( 'Contact section', 'trustusbro-site-manager' ),
					'icon'        => 'dashicons-email',
					'description' => __( 'Contact details come from Contact Information Manager.', 'trustusbro-site-manager' ),
					'source'      => 'contact',
					'fields'      => array(
						'eyebrow'      => $eyebrow_field,
						'heading'      => array(
							'type'    => 'text',
							'label'   => __( 'Heading', 'trustusbro-site-manager' ),
							'default' => __( 'Get in touch', 'trustusbro-site-manager' ),
						),
						'text'         => array(
							'type'  => 'textarea',
							'label' => __( 'Intro text', 'trustusbro-site-manager' ),
						),
						'form_heading' => array(
							'type'    => 'text',
							'label'   => __( 'Form heading', 'trustusbro-site-manager' ),
							'default' => __( 'Send us a message', 'trustusbro-site-manager' ),
						),
						'show_form'    => array(
							'type'    => 'toggle',
							'label'   => __( 'Show contact form', 'trustusbro-site-manager' ),
							'help'    => __( 'Embeds a form from Contact Form 7, WPForms or another plugin using the shortcode below.', 'trustusbro-site-manager' ),
							'default' => true,
						),
						'form_shortcode' => array(
							'type'  => 'text',
							'label' => __( 'Form shortcode', 'trustusbro-site-manager' ),
							'help'  => __( 'Paste the shortcode of your form plugin, e.g. [contact-form-7 id="123"]. Leave blank to link to your contact page instead.', 'trustusbro-site-manager' ),
						),
					),
				),
				'text_block'   => array(
					'label'       => __( 'Text block', 'trustusbro-site-manager' ),
					'icon'        => 'dashicons-editor-paragraph',
					'description' => __( 'A flexible heading, rich text and optional button.', 'trustusbro-site-manager' ),
					'fields'      => array(
						'eyebrow' => $eyebrow_field,
						'heading' => array(
							'type'  => 'text',
							'label' => __( 'Heading', 'trustusbro-site-manager' ),
						),
						'text'    => array(
							'type'      => 'html',
							'label'     => __( 'Text', 'trustusbro-site-manager' ),
							'help'      => __( 'Basic formatting is allowed: bold, italic, links and lists.', 'trustusbro-site-manager' ),
						),
						'align'   => array(
							'type'    => 'select',
							'label'   => __( 'Alignment', 'trustusbro-site-manager' ),
							'options' => array(
								'left'   => __( 'Left', 'trustusbro-site-manager' ),
								'center' => __( 'Centre', 'trustusbro-site-manager' ),
							),
							'default' => 'left',
						),
						'button'  => array(
							'type'   => 'group',
							'label'  => __( 'Button', 'trustusbro-site-manager' ),
							'fields' => $link_fields,
						),
					),
				),
			),
		);

		/*
		 * ---------------------------------------------------------------
		 * About page (sections)
		 * ---------------------------------------------------------------
		 */
		$schema['about'] = array(
			'label'    => __( 'About page', 'trustusbro-site-manager' ),
			'type'     => 'sections',
			'icon'     => 'dashicons-info-outline',
			'sections' => array(
				'intro'    => array(
					'label'       => __( 'Intro', 'trustusbro-site-manager' ),
					'icon'        => 'dashicons-format-aside',
					'description' => __( 'Page heading and story.', 'trustusbro-site-manager' ),
					'supports'    => array( 'image' ),
					'fields'      => array(
						'eyebrow' => $eyebrow_field,
						'heading' => array(
							'type'    => 'text',
							'label'   => __( 'Heading', 'trustusbro-site-manager' ),
							'default' => __( 'About us', 'trustusbro-site-manager' ),
						),
						'text'    => array(
							'type'  => 'html',
							'label' => __( 'Story', 'trustusbro-site-manager' ),
						),
						'image'   => array(
							'type'  => 'image',
							'label' => __( 'Image', 'trustusbro-site-manager' ),
						),
					),
				),
				'values'   => array(
					'label'       => __( 'Values', 'trustusbro-site-manager' ),
					'icon'        => 'dashicons-awards',
					'description' => __( 'Value cards.', 'trustusbro-site-manager' ),
					'fields'      => array(
						'heading' => array(
							'type'    => 'text',
							'label'   => __( 'Heading', 'trustusbro-site-manager' ),
							'default' => __( 'What we value', 'trustusbro-site-manager' ),
						),
						'items'   => array(
							'type'   => 'repeater',
							'label'  => __( 'Values', 'trustusbro-site-manager' ),
							'fields' => array(
								'letter' => array(
									'type'  => 'text',
									'label' => __( 'Short marker', 'trustusbro-site-manager' ),
									'help'  => __( 'One letter or number shown on the card, optional.', 'trustusbro-site-manager' ),
								),
								'title'  => array(
									'type'  => 'text',
									'label' => __( 'Title', 'trustusbro-site-manager' ),
								),
								'text'   => array(
									'type'  => 'textarea',
									'label' => __( 'Description', 'trustusbro-site-manager' ),
								),
							),
							'max'    => 12,
						),
					),
				),
				'timeline' => array(
					'label'       => __( 'History / timeline', 'trustusbro-site-manager' ),
					'icon'        => 'dashicons-backup',
					'description' => __( 'Milestones in order.', 'trustusbro-site-manager' ),
					'fields'      => array(
						'heading' => array(
							'type'    => 'text',
							'label'   => __( 'Heading', 'trustusbro-site-manager' ),
							'default' => __( 'Our story so far', 'trustusbro-site-manager' ),
						),
						'items'   => array(
							'type'   => 'repeater',
							'label'  => __( 'Milestones', 'trustusbro-site-manager' ),
							'fields' => array(
								'year'  => array(
									'type'  => 'text',
									'label' => __( 'Year / label', 'trustusbro-site-manager' ),
								),
								'title' => array(
									'type'  => 'text',
									'label' => __( 'Title', 'trustusbro-site-manager' ),
								),
								'text'  => array(
									'type'  => 'textarea',
									'label' => __( 'Description', 'trustusbro-site-manager' ),
								),
							),
							'max'    => 20,
						),
					),
				),
				'cta'      => array(
					'label'       => __( 'Call to action', 'trustusbro-site-manager' ),
					'icon'        => 'dashicons-megaphone',
					'description' => __( 'Centred prompt with buttons.', 'trustusbro-site-manager' ),
					'fields'      => array(
						'heading' => array(
							'type'    => 'text',
							'label'   => __( 'Heading', 'trustusbro-site-manager' ),
							'default' => __( 'Ready to start?', 'trustusbro-site-manager' ),
						),
						'text'    => array(
							'type'  => 'textarea',
							'label' => __( 'Text', 'trustusbro-site-manager' ),
						),
						'buttons' => array(
							'type'   => 'repeater',
							'label'  => __( 'Buttons', 'trustusbro-site-manager' ),
							'fields' => $link_fields,
							'max'    => 2,
						),
					),
				),
			),
		);

		/*
		 * ---------------------------------------------------------------
		 * Collections
		 * ---------------------------------------------------------------
		 */
		$schema['services'] = array(
			'label'       => __( 'Services', 'trustusbro-site-manager' ),
			'type'        => 'collection',
			'icon'        => 'dashicons-screenoptions',
			'item_label'  => __( 'service', 'trustusbro-site-manager' ),
			'description' => __( 'Each service becomes a card wherever the Services section is used.', 'trustusbro-site-manager' ),
			'item_fields' => array(
				'title'    => array(
					'type'     => 'text',
					'label'    => __( 'Service name', 'trustusbro-site-manager' ),
					'required' => true,
				),
				'summary'  => array(
					'type'  => 'textarea',
					'label' => __( 'Short description', 'trustusbro-site-manager' ),
				),
				'icon'     => array(
					'type'    => 'select',
					'label'   => __( 'Icon', 'trustusbro-site-manager' ),
					'options' => array(
						''          => __( 'No icon', 'trustusbro-site-manager' ),
						'design'    => __( 'Design', 'trustusbro-site-manager' ),
						'code'      => __( 'Development', 'trustusbro-site-manager' ),
						'search'    => __( 'Research', 'trustusbro-site-manager' ),
						'chart'     => __( 'Growth / marketing', 'trustusbro-site-manager' ),
						'sparkle'   => __( 'Creative', 'trustusbro-site-manager' ),
						'settings'  => __( 'Support', 'trustusbro-site-manager' ),
						'camera'    => __( 'Media', 'trustusbro-site-manager' ),
						'briefcase' => __( 'Consulting', 'trustusbro-site-manager' ),
					),
				),
				'image'    => array(
					'type'  => 'image',
					'label' => __( 'Card image', 'trustusbro-site-manager' ),
				),
				'features' => array(
					'type'   => 'repeater',
					'label'  => __( 'Bullet points', 'trustusbro-site-manager' ),
					'fields' => array(
						'text' => array(
							'type'  => 'text',
							'label' => __( 'Point', 'trustusbro-site-manager' ),
						),
					),
					'max'    => 8,
				),
				'button'   => array(
					'type'   => 'group',
					'label'  => __( 'Card button', 'trustusbro-site-manager' ),
					'fields' => array(
						'label' => array(
							'type'  => 'text',
							'label' => __( 'Label', 'trustusbro-site-manager' ),
						),
						'url'   => array(
							'type'  => 'url',
							'label' => __( 'Link', 'trustusbro-site-manager' ),
						),
					),
				),
			),
		);

		$schema['industries'] = array(
			'label'       => __( 'Industries', 'trustusbro-site-manager' ),
			'type'        => 'collection',
			'icon'        => 'dashicons-building',
			'item_label'  => __( 'industry', 'trustusbro-site-manager' ),
			'item_fields' => array(
				'title'   => array(
					'type'     => 'text',
					'label'    => __( 'Industry name', 'trustusbro-site-manager' ),
					'required' => true,
				),
				'summary' => array(
					'type'  => 'textarea',
					'label' => __( 'Description', 'trustusbro-site-manager' ),
				),
				'image'   => array(
					'type'  => 'image',
					'label' => __( 'Image', 'trustusbro-site-manager' ),
				),
				'url'     => array(
					'type'  => 'url',
					'label' => __( 'Link', 'trustusbro-site-manager' ),
				),
			),
		);

		$schema['case_studies'] = array(
			'label'       => __( 'Case studies', 'trustusbro-site-manager' ),
			'type'        => 'collection',
			'icon'        => 'dashicons-portfolio',
			'item_label'  => __( 'case study', 'trustusbro-site-manager' ),
			'item_fields' => array(
				'title'   => array(
					'type'     => 'text',
					'label'    => __( 'Project title', 'trustusbro-site-manager' ),
					'required' => true,
				),
				'client'  => array(
					'type'  => 'text',
					'label' => __( 'Client', 'trustusbro-site-manager' ),
				),
				'summary' => array(
					'type'  => 'textarea',
					'label' => __( 'Summary', 'trustusbro-site-manager' ),
				),
				'result'  => array(
					'type'  => 'text',
					'label' => __( 'Headline result', 'trustusbro-site-manager' ),
					'help'  => __( 'A short outcome, e.g. "+38% sign-ups".', 'trustusbro-site-manager' ),
				),
				'image'   => array(
					'type'  => 'image',
					'label' => __( 'Cover image', 'trustusbro-site-manager' ),
				),
				'url'     => array(
					'type'  => 'url',
					'label' => __( 'Link to case study', 'trustusbro-site-manager' ),
				),
				'tags'    => array(
					'type'  => 'text',
					'label' => __( 'Tags', 'trustusbro-site-manager' ),
					'help'  => __( 'Comma separated, e.g. Strategy, UX, Web.', 'trustusbro-site-manager' ),
				),
			),
		);

		$schema['testimonials'] = array(
			'label'       => __( 'Testimonials', 'trustusbro-site-manager' ),
			'type'        => 'collection',
			'icon'        => 'dashicons-format-quote',
			'item_label'  => __( 'testimonial', 'trustusbro-site-manager' ),
			'item_fields' => array(
				'quote'   => array(
					'type'     => 'textarea',
					'label'    => __( 'Quote', 'trustusbro-site-manager' ),
					'required' => true,
				),
				'name'    => array(
					'type'  => 'text',
					'label' => __( 'Person name', 'trustusbro-site-manager' ),
				),
				'role'    => array(
					'type'  => 'text',
					'label' => __( 'Role / company', 'trustusbro-site-manager' ),
				),
				'avatar'  => array(
					'type'  => 'image',
					'label' => __( 'Photo', 'trustusbro-site-manager' ),
				),
				'rating'  => array(
					'type'    => 'number',
					'label'   => __( 'Rating out of 5', 'trustusbro-site-manager' ),
					'min'     => 0,
					'max'     => 5,
					'default' => 5,
				),
			),
		);

		$schema['faq'] = array(
			'label'       => __( 'FAQ', 'trustusbro-site-manager' ),
			'type'        => 'collection',
			'icon'        => 'dashicons-editor-help',
			'item_label'  => __( 'question', 'trustusbro-site-manager' ),
			'item_fields' => array(
				'question' => array(
					'type'     => 'text',
					'label'    => __( 'Question', 'trustusbro-site-manager' ),
					'required' => true,
				),
				'answer'   => array(
					'type'  => 'html',
					'label' => __( 'Answer', 'trustusbro-site-manager' ),
				),
			),
		);

		/*
		 * ---------------------------------------------------------------
		 * Header / footer / contact / SEO / design records
		 * ---------------------------------------------------------------
		 */
		$schema['header'] = array(
			'label'  => __( 'Header', 'trustusbro-site-manager' ),
			'type'   => 'record',
			'icon'   => 'dashicons-align-center',
			'fields' => array(
				'logo'          => array(
					'type'  => 'image',
					'label' => __( 'Logo image', 'trustusbro-site-manager' ),
					'help'  => __( 'Leave empty to use your theme logo, then the site title.', 'trustusbro-site-manager' ),
				),
				'logo_text'     => array(
					'type'  => 'text',
					'label' => __( 'Logo text', 'trustusbro-site-manager' ),
					'help'  => __( 'Shown when no logo image is set. Defaults to the site title.', 'trustusbro-site-manager' ),
				),
				'logo_url'      => array(
					'type'    => 'url',
					'label'   => __( 'Logo link', 'trustusbro-site-manager' ),
					'default' => '',
				),
				'menu_items'    => array(
					'type'   => 'repeater',
					'label'  => __( 'Menu items', 'trustusbro-site-manager' ),
					'fields' => array(
						'label' => array(
							'type'     => 'text',
							'label'    => __( 'Label', 'trustusbro-site-manager' ),
							'required' => true,
						),
						'url'   => array(
							'type'  => 'url',
							'label' => __( 'Link', 'trustusbro-site-manager' ),
						),
						'children' => array(
							'type'   => 'repeater',
							'label'  => __( 'Dropdown items', 'trustusbro-site-manager' ),
							'fields' => array(
								'label' => array(
									'type'  => 'text',
									'label' => __( 'Label', 'trustusbro-site-manager' ),
								),
								'url'   => array(
									'type'  => 'url',
									'label' => __( 'Link', 'trustusbro-site-manager' ),
								),
							),
							'max'    => 10,
						),
					),
					'max'    => 12,
				),
				'cta'           => array(
					'type'   => 'group',
					'label'  => __( 'Header button', 'trustusbro-site-manager' ),
					'fields' => $link_fields,
				),
				'sticky'        => array(
					'type'    => 'toggle',
					'label'   => __( 'Stick header to top when scrolling', 'trustusbro-site-manager' ),
					'default' => true,
				),
				'transparent'   => array(
					'type'    => 'toggle',
					'label'   => __( 'Transparent header over the hero', 'trustusbro-site-manager' ),
					'default' => false,
				),
				'mobile_label'  => array(
					'type'    => 'text',
					'label'   => __( 'Mobile menu button label', 'trustusbro-site-manager' ),
					'default' => __( 'Menu', 'trustusbro-site-manager' ),
				),
				'use_wp_menu'   => array(
					'type'    => 'toggle',
					'label'   => __( 'Use a WordPress menu instead of the items above', 'trustusbro-site-manager' ),
					'help'    => __( 'Pick which WordPress menu to show in Design Settings.', 'trustusbro-site-manager' ),
					'default' => false,
				),
			),
		);

		$schema['footer'] = array(
			'label'  => __( 'Footer', 'trustusbro-site-manager' ),
			'type'   => 'record',
			'icon'   => 'dashicons-align-wide',
			'fields' => array(
				'logo'           => array(
					'type'  => 'image',
					'label' => __( 'Footer logo', 'trustusbro-site-manager' ),
				),
				'tagline'        => array(
					'type'  => 'text',
					'label' => __( 'Tagline', 'trustusbro-site-manager' ),
				),
				'description'    => array(
					'type'  => 'textarea',
					'label' => __( 'Agency description', 'trustusbro-site-manager' ),
				),
				'social'         => array(
					'type'   => 'repeater',
					'label'  => __( 'Social links', 'trustusbro-site-manager' ),
					'fields' => array(
						'network' => array(
							'type'    => 'select',
							'label'   => __( 'Network', 'trustusbro-site-manager' ),
							'options' => array(
								'instagram' => 'Instagram',
								'linkedin'  => 'LinkedIn',
								'x'         => 'X / Twitter',
								'facebook'  => 'Facebook',
								'youtube'   => 'YouTube',
								'behance'   => 'Behance',
								'dribbble'  => 'Dribbble',
								'whatsapp'  => 'WhatsApp',
								'other'     => __( 'Other', 'trustusbro-site-manager' ),
							),
						),
						'label'   => array(
							'type'  => 'text',
							'label' => __( 'Accessible label', 'trustusbro-site-manager' ),
						),
						'url'     => array(
							'type'  => 'url',
							'label' => __( 'Profile URL', 'trustusbro-site-manager' ),
						),
					),
					'max'    => 10,
				),
				'columns'        => array(
					'type'   => 'repeater',
					'label'  => __( 'Link columns', 'trustusbro-site-manager' ),
					'help'   => __( 'The approved four-column footer: brand column plus up to three link columns.', 'trustusbro-site-manager' ),
					'fields' => array(
						'title' => array(
							'type'  => 'text',
							'label' => __( 'Column heading', 'trustusbro-site-manager' ),
						),
						'links' => array(
							'type'   => 'repeater',
							'label'  => __( 'Links', 'trustusbro-site-manager' ),
							'fields' => array(
								'label' => array(
									'type'  => 'text',
									'label' => __( 'Label', 'trustusbro-site-manager' ),
								),
								'url'   => array(
									'type'  => 'url',
									'label' => __( 'Link', 'trustusbro-site-manager' ),
								),
							),
							'max'    => 12,
						),
					),
					'max'    => 3,
				),
				'email'          => array(
					'type'  => 'email',
					'label' => __( 'Email address', 'trustusbro-site-manager' ),
				),
				'phone'          => array(
					'type'  => 'tel',
					'label' => __( 'Mobile number', 'trustusbro-site-manager' ),
				),
				'address'        => array(
					'type'  => 'textarea',
					'label' => __( 'Address', 'trustusbro-site-manager' ),
				),
				'copyright'      => array(
					'type'    => 'text',
					'label'   => __( 'Copyright line', 'trustusbro-site-manager' ),
					'help'    => __( 'Use {year} to insert the current year automatically.', 'trustusbro-site-manager' ),
					'default' => '© {year} {site}',
				),
				'legal_links'    => array(
					'type'   => 'repeater',
					'label'  => __( 'Legal links', 'trustusbro-site-manager' ),
					'fields' => array(
						'label' => array(
							'type'  => 'text',
							'label' => __( 'Label', 'trustusbro-site-manager' ),
						),
						'url'   => array(
							'type'  => 'url',
							'label' => __( 'Link', 'trustusbro-site-manager' ),
						),
					),
					'max'    => 6,
				),
			),
		);

		$schema['contact'] = array(
			'label'  => __( 'Contact information', 'trustusbro-site-manager' ),
			'type'   => 'record',
			'icon'   => 'dashicons-email-alt',
			'fields' => array(
				'email'        => array(
					'type'  => 'email',
					'label' => __( 'Email address', 'trustusbro-site-manager' ),
				),
				'phone'        => array(
					'type'  => 'tel',
					'label' => __( 'Phone number', 'trustusbro-site-manager' ),
				),
				'whatsapp'     => array(
					'type'  => 'tel',
					'label' => __( 'WhatsApp number', 'trustusbro-site-manager' ),
				),
				'address'      => array(
					'type'  => 'textarea',
					'label' => __( 'Address', 'trustusbro-site-manager' ),
				),
				'hours'        => array(
					'type'  => 'text',
					'label' => __( 'Working hours', 'trustusbro-site-manager' ),
				),
				'map_embed'    => array(
					'type'  => 'url',
					'label' => __( 'Map embed URL', 'trustusbro-site-manager' ),
					'help'  => __( 'Paste the src URL from a Google Maps embed iframe.', 'trustusbro-site-manager' ),
				),
				'recipient'    => array(
					'type'  => 'email',
					'label' => __( 'Form notification email', 'trustusbro-site-manager' ),
					'help'  => __( 'Used by the built-in contact form fallback.', 'trustusbro-site-manager' ),
				),
				'social'       => array(
					'type'   => 'repeater',
					'label'  => __( 'Social profiles', 'trustusbro-site-manager' ),
					'fields' => array(
						'network' => array(
							'type'    => 'select',
							'label'   => __( 'Network', 'trustusbro-site-manager' ),
							'options' => array(
								'instagram' => 'Instagram',
								'linkedin'  => 'LinkedIn',
								'x'         => 'X / Twitter',
								'facebook'  => 'Facebook',
								'youtube'   => 'YouTube',
								'behance'   => 'Behance',
								'dribbble'  => 'Dribbble',
								'other'     => __( 'Other', 'trustusbro-site-manager' ),
							),
						),
						'url'     => array(
							'type'  => 'url',
							'label' => __( 'Profile URL', 'trustusbro-site-manager' ),
						),
					),
					'max'    => 10,
				),
			),
		);

		$schema['seo'] = array(
			'label'  => __( 'SEO defaults', 'trustusbro-site-manager' ),
			'type'   => 'record',
			'icon'   => 'dashicons-search',
			'fields' => array(
				'title_suffix'   => array(
					'type'    => 'text',
					'label'   => __( 'Title suffix', 'trustusbro-site-manager' ),
					'help'    => __( 'Appended to page titles, e.g. " | TrustUsBro".', 'trustusbro-site-manager' ),
					'default' => ' | {site}',
				),
				'meta_description' => array(
					'type'  => 'textarea',
					'label' => __( 'Default meta description', 'trustusbro-site-manager' ),
				),
				'og_image'       => array(
					'type'  => 'image',
					'label' => __( 'Default social sharing image', 'trustusbro-site-manager' ),
				),
				'twitter_handle' => array(
					'type'  => 'text',
					'label' => __( 'Twitter/X handle', 'trustusbro-site-manager' ),
				),
				'organization'   => array(
					'type'  => 'text',
					'label' => __( 'Organisation name for schema', 'trustusbro-site-manager' ),
				),
				'logo'           => array(
					'type'  => 'image',
					'label' => __( 'Organisation logo for schema', 'trustusbro-site-manager' ),
				),
				'noindex'        => array(
					'type'    => 'toggle',
					'label'   => __( 'Ask search engines not to index this site', 'trustusbro-site-manager' ),
					'help'    => __( 'Only enable on staging. This also blocks indexing in WordPress settings.', 'trustusbro-site-manager' ),
					'default' => false,
				),
				'schema_types'   => array(
					'type'   => 'repeater',
					'label'  => __( 'Extra schema topics (sameAs links)', 'trustusbro-site-manager' ),
					'fields' => array(
						'url' => array(
							'type'  => 'url',
							'label' => __( 'Profile URL', 'trustusbro-site-manager' ),
						),
					),
					'max'    => 10,
				),
			),
		);

		$schema['design'] = array(
			'label'  => __( 'Design tokens', 'trustusbro-site-manager' ),
			'type'   => 'record',
			'icon'   => 'dashicons-art',
			'fields' => array(
				'color_text'       => array(
					'type'    => 'color',
					'label'   => __( 'Body text colour', 'trustusbro-site-manager' ),
					'help'    => __( 'Leave empty to inherit the active theme.', 'trustusbro-site-manager' ),
				),
				'color_heading'    => array(
					'type'  => 'color',
					'label' => __( 'Heading colour', 'trustusbro-site-manager' ),
				),
				'color_muted'      => array(
					'type'  => 'color',
					'label' => __( 'Muted text colour', 'trustusbro-site-manager' ),
				),
				'color_accent'     => array(
					'type'  => 'color',
					'label' => __( 'Accent colour', 'trustusbro-site-manager' ),
				),
				'color_accent_text'=> array(
					'type'  => 'color',
					'label' => __( 'Text on accent', 'trustusbro-site-manager' ),
				),
				'color_surface'    => array(
					'type'  => 'color',
					'label' => __( 'Card background', 'trustusbro-site-manager' ),
				),
				'color_border'     => array(
					'type'  => 'color',
					'label' => __( 'Border colour', 'trustusbro-site-manager' ),
				),
				'color_bg'         => array(
					'type'  => 'color',
					'label' => __( 'Page background', 'trustusbro-site-manager' ),
				),
				'font_body'        => array(
					'type'  => 'font',
					'label' => __( 'Body font stack', 'trustusbro-site-manager' ),
				),
				'font_heading'     => array(
					'type'  => 'font',
					'label' => __( 'Heading font stack', 'trustusbro-site-manager' ),
				),
				'font_mono'        => array(
					'type'  => 'font',
					'label' => __( 'Monospace font stack', 'trustusbro-site-manager' ),
				),
				'radius'           => array(
					'type'    => 'css_length',
					'label'   => __( 'Corner radius', 'trustusbro-site-manager' ),
					'help'    => __( 'Use 0 to keep the approved rectangular grid look.', 'trustusbro-site-manager' ),
					'default' => '0',
				),
				'container_width'  => array(
					'type'    => 'css_length',
					'label'   => __( 'Content width', 'trustusbro-site-manager' ),
					'default' => '1280px',
				),
				'section_space'    => array(
					'type'    => 'css_length',
					'label'   => __( 'Vertical section spacing', 'trustusbro-site-manager' ),
					'default' => '96px',
				),
				'button_style'     => array(
					'type'    => 'select',
					'label'   => __( 'Button corners', 'trustusbro-site-manager' ),
					'options' => array(
						'square' => __( 'Square (approved default)', 'trustusbro-site-manager' ),
						'soft'   => __( 'Slightly rounded', 'trustusbro-site-manager' ),
						'pill'   => __( 'Pill', 'trustusbro-site-manager' ),
					),
					'default' => 'square',
				),
				'show_branding'    => array(
					'type'    => 'toggle',
					'label'   => __( 'Render the header and footer from Site Manager', 'trustusbro-site-manager' ),
					'help'    => __( 'Off by default: your theme keeps its own header and footer, so nothing is duplicated. Turn this on only after you have checked your theme header is not needed, or use the TrustUsBro header/footer blocks in the Site Editor instead.', 'trustusbro-site-manager' ),
					'default' => false,
				),
				'header_menu'      => array(
					'type'    => 'select',
					'label'   => __( 'WordPress menu used in the header', 'trustusbro-site-manager' ),
					'options' => array( '' => __( '— Select a menu —', 'trustusbro-site-manager' ) ),
				),
				'front_page'       => array(
					'type'    => 'toggle',
					'label'   => __( 'Use Site Manager sections for the front page', 'trustusbro-site-manager' ),
					'help'    => __( 'Replaces the page content filter-free, via the theme\'s normal template.', 'trustusbro-site-manager' ),
					'default' => false,
				),
				'about_page'       => array(
					'type'    => 'number',
					'label'   => __( 'About page ID', 'trustusbro-site-manager' ),
					'help'    => __( 'The page that should render the About sections.', 'trustusbro-site-manager' ),
					'default' => 0,
					'min'     => 0,
				),
				'legacy_docs'      => array(
					'type'  => 'text',
					'label' => __( 'Legacy section keys', 'trustusbro-site-manager' ),
					'help'  => __( 'Comma separated keys of retired sections. They stay editable but are never rendered.', 'trustusbro-site-manager' ),
				),
			),
		);

		return $schema;
	}

	/**
	 * Field map for a document type. Used by sanitizers.
	 *
	 * @param string $doc_key Document key.
	 * @return array
	 */
	public static function fields_for( $doc_key ) {
		$doc = self::doc( $doc_key );
		if ( ! $doc ) {
			return array();
		}
		if ( 'sections' === tusb_arr( $doc, 'type' ) ) {
			$map = array();
			foreach ( $doc['sections'] as $type => $section ) {
				$map[ $type ] = isset( $section['fields'] ) ? $section['fields'] : array();
			}
			return $map;
		}
		if ( 'collection' === tusb_arr( $doc, 'type' ) ) {
			return isset( $doc['item_fields'] ) ? $doc['item_fields'] : array();
		}
		return isset( $doc['fields'] ) ? $doc['fields'] : array();
	}
}
