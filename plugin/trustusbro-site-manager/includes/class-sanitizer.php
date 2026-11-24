<?php
/**
 * Schema-driven sanitisation and validation.
 *
 * All writes from the dashboard or REST API pass through here. Nothing is
 * trusted: unknown fields are dropped, wrong types are rejected, and rich text
 * is filtered with a restricted kses allowlist.
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

/**
 * Sanitizer.
 */
class TUSB_Sanitizer {

	/**
	 * Allowed HTML for rich text fields. Deliberately narrow: the approved
	 * design uses simple paragraphs, emphasis, links and lists.
	 *
	 * @return array
	 */
	public static function kses_allowed() {
		$allowed = array(
			'a'          => array(
				'href'   => true,
				'title'  => true,
				'target' => true,
				'rel'    => true,
			),
			'strong'     => array(),
			'b'          => array(),
			'em'         => array(),
			'i'          => array(),
			'u'          => array(),
			's'          => array(),
			'br'         => array(),
			'p'          => array(),
			'span'       => array( 'class' => true ),
			'ul'         => array( 'class' => true ),
			'ol'         => array( 'class' => true ),
			'li'         => array(),
			'h2'         => array( 'class' => true ),
			'h3'         => array( 'class' => true ),
			'h4'         => array( 'class' => true ),
			'blockquote' => array( 'class' => true ),
			'code'       => array(),
			'pre'        => array(),
		);
		/**
		 * Filter the allowed HTML for rich text fields.
		 *
		 * @param array $allowed Allowed tags.
		 */
		return apply_filters( 'tusb_kses_allowed', $allowed );
	}

	/**
	 * Sanitise a full document payload.
	 *
	 * @param string $doc_key Document key.
	 * @param array  $input Raw input.
	 * @return array|WP_Error
	 */
	public static function document( $doc_key, $input ) {
		$doc = TUSB_Schema::doc( $doc_key );
		if ( ! $doc ) {
			return new WP_Error( 'tusb_unknown_doc', __( 'Unknown document.', 'trustusbro-site-manager' ), array( 'status' => 404 ) );
		}

		if ( ! is_array( $input ) ) {
			return new WP_Error( 'tusb_invalid_payload', __( 'The submitted content could not be read. Please try again.', 'trustusbro-site-manager' ), array( 'status' => 400 ) );
		}

		$type = tusb_arr( $doc, 'type' );

		if ( 'sections' === $type ) {
			return self::sections( $doc_key, $input, $doc );
		}

		if ( 'collection' === $type ) {
			return self::collection( $doc_key, $input, $doc );
		}

		return self::record( $doc_key, $input, $doc );
	}

	/**
	 * Sanitise a sections document.
	 *
	 * @param string $doc_key Document key.
	 * @param array  $input Input.
	 * @param array  $doc Doc definition.
	 * @return array|WP_Error
	 */
	private static function sections( $doc_key, $input, $doc ) {
		$definitions = $doc['sections'];
		$incoming    = isset( $input['sections'] ) && is_array( $input['sections'] ) ? $input['sections'] : array();
		$out         = array();
		$errors      = array();
		$seen_ids    = array();

		foreach ( $incoming as $raw_section ) {
			if ( ! is_array( $raw_section ) ) {
				continue;
			}
			$section_type = isset( $raw_section['type'] ) ? sanitize_key( $raw_section['type'] ) : '';
			if ( ! $section_type || ! isset( $definitions[ $section_type ] ) ) {
				continue; // Unknown section types are dropped, never persisted.
			}

			$id = isset( $raw_section['id'] ) ? sanitize_key( $raw_section['id'] ) : '';
			if ( '' === $id || isset( $seen_ids[ $id ] ) ) {
				$id = self::unique_id( $section_type, $seen_ids );
			}
			$seen_ids[ $id ] = true;

			$fields = self::fields(
				$definitions[ $section_type ]['fields'],
				$raw_section,
				$section_type,
				$errors,
				$doc_key
			);

			$out[] = array_merge(
				array(
					'id'      => $id,
					'type'    => $section_type,
					'enabled' => ! empty( $raw_section['enabled'] ),
				),
				$fields
			);
		}

		if ( $errors ) {
			return new WP_Error(
				'tusb_validation_failed',
				implode( ' ', $errors ),
				array(
					'status' => 422,
					'errors' => $errors,
				)
			);
		}

		return array( 'sections' => $out );
	}

	/**
	 * Sanitise a collection document.
	 *
	 * @param string $doc_key Document key.
	 * @param array  $input Input.
	 * @param array  $doc Doc definition.
	 * @return array|WP_Error
	 */
	private static function collection( $doc_key, $input, $doc ) {
		$incoming = isset( $input['items'] ) && is_array( $input['items'] ) ? $input['items'] : array();
		$fields   = $doc['item_fields'];
		$out      = array();
		$errors   = array();
		$seen_ids = array();

		foreach ( $incoming as $raw_item ) {
			if ( ! is_array( $raw_item ) ) {
				continue;
			}
			$id = isset( $raw_item['id'] ) ? sanitize_key( $raw_item['id'] ) : '';
			if ( '' === $id || isset( $seen_ids[ $id ] ) ) {
				$id = self::unique_id( 'item', $seen_ids );
			}
			$seen_ids[ $id ] = true;

			$item_errors = array();
			$values      = self::fields( $fields, $raw_item, '', $item_errors, $doc_key );
			$errors      = array_merge( $errors, $item_errors );

			$out[] = array_merge(
				array(
					'id'      => $id,
					'visible' => ! isset( $raw_item['visible'] ) || ! empty( $raw_item['visible'] ),
				),
				$values
			);
		}

		if ( $errors ) {
			return new WP_Error(
				'tusb_validation_failed',
				implode( ' ', $errors ),
				array(
					'status' => 422,
					'errors' => $errors,
				)
			);
		}

		return array( 'items' => $out );
	}

	/**
	 * Sanitise a record document.
	 *
	 * @param string $doc_key Document key.
	 * @param array  $input Input.
	 * @param array  $doc Doc definition.
	 * @return array|WP_Error
	 */
	private static function record( $doc_key, $input, $doc ) {
		$errors = array();
		if ( isset( $input['fields'] ) && is_array( $input['fields'] ) ) {
			$input = $input['fields'];
		}
		$values = self::fields( $doc['fields'], $input, '', $errors, $doc_key );

		if ( $errors ) {
			return new WP_Error(
				'tusb_validation_failed',
				implode( ' ', $errors ),
				array(
					'status' => 422,
					'errors' => $errors,
				)
			);
		}

		return $values;
	}

	/**
	 * Sanitise a field map.
	 *
	 * @param array  $fields Field definitions.
	 * @param array  $input Raw input values.
	 * @param string $context Context label for errors.
	 * @param array  $errors Error collector (by reference).
	 * @param string $doc_key Document key.
	 * @return array
	 */
	public static function fields( $fields, $input, $context = '', &$errors = array(), $doc_key = '' ) {
		$out = array();
		foreach ( (array) $fields as $key => $field ) {
			$label = isset( $field['label'] ) ? $field['label'] : $key;
			if ( $context ) {
				$label = $context . ': ' . $label;
			}
			$value = is_array( $input ) && array_key_exists( $key, $input ) ? $input[ $key ] : TUSB_Schema::field_default( $field );
			$clean = self::value( $field, $value, $label, $errors, $doc_key );

			if ( is_wp_error( $clean ) ) {
				$errors[] = $clean->get_error_message();
				$clean    = TUSB_Schema::field_default( $field );
			}
			$out[ $key ] = $clean;
		}
		return $out;
	}

	/**
	 * Sanitise one value.
	 *
	 * @param array  $field Field definition.
	 * @param mixed  $value Raw value.
	 * @param string $label Human label for errors.
	 * @param array  $errors Error collector.
	 * @param string $doc_key Document key.
	 * @return mixed|WP_Error
	 */
	public static function value( $field, $value, $label, &$errors = array(), $doc_key = '' ) {
		$type     = isset( $field['type'] ) ? $field['type'] : 'text';
		$required = ! empty( $field['required'] );

		$clean = '';

		switch ( $type ) {
			case 'textarea':
				$raw   = is_scalar( $value ) ? (string) $value : '';
				$clean = sanitize_textarea_field( $raw );
				$clean = self::limit_length( $clean, 20000 );
				break;

			case 'html':
				$raw   = is_scalar( $value ) ? (string) $value : '';
				$clean = wp_kses( $raw, self::kses_allowed() );
				$clean = wpautop( $clean );
				break;

			case 'url':
				$clean = self::url( $value );
				break;

			case 'email':
				$raw   = is_scalar( $value ) ? trim( (string) $value ) : '';
				$clean = '' === $raw ? '' : sanitize_email( $raw );
				if ( '' !== $raw && ! is_email( $clean ) ) {
					return new WP_Error( 'tusb_bad_email', sprintf(
						/* translators: %s: field label. */
						__( '%s: please enter a valid email address.', 'trustusbro-site-manager' ),
						$label
					) );
				}
				break;

			case 'tel':
				$raw   = is_scalar( $value ) ? (string) $value : '';
				$clean = trim( preg_replace( '/[^0-9+\-()\s.]/', '', $raw ) );
				$clean = self::limit_length( $clean, 32 );
				break;

			case 'image':
				$clean = self::image_id( $value );
				break;

			case 'select':
				$options = isset( $field['options'] ) && is_array( $field['options'] ) ? $field['options'] : array();
				$raw     = is_scalar( $value ) ? sanitize_key( (string) $value ) : '';
				if ( array_key_exists( $raw, $options ) ) {
					$clean = $raw;
				} else {
					$clean = (string) TUSB_Schema::field_default( $field );
				}
				break;

			case 'toggle':
				$clean = self::to_bool( $value );
				break;

			case 'number':
				$min   = isset( $field['min'] ) ? (int) $field['min'] : null;
				$max   = isset( $field['max'] ) ? (int) $field['max'] : null;
				$clean = (int) ( is_numeric( $value ) ? $value : 0 );
				if ( null !== $min && $clean < $min ) {
					$clean = $min;
				}
				if ( null !== $max && $clean > $max ) {
					$clean = $max;
				}
				break;

			case 'color':
				$clean = tusb_sanitize_color( is_scalar( $value ) ? $value : '' );
				break;

			case 'css_length':
				$clean = tusb_sanitize_css_length( is_scalar( $value ) ? $value : '' );
				break;

			case 'font':
				$clean = tusb_sanitize_font_family( is_scalar( $value ) ? $value : '' );
				break;

			case 'hidden':
				$clean = sanitize_text_field( is_scalar( $value ) ? (string) $value : '' );
				break;

			case 'group':
				$sub    = isset( $field['fields'] ) ? $field['fields'] : array();
				$raw    = is_array( $value ) ? $value : array();
				$clean  = self::fields( $sub, $raw, $label, $errors, $doc_key );
				break;

			case 'repeater':
				$clean = self::repeater( $field, $value, $label, $errors, $doc_key );
				if ( is_wp_error( $clean ) ) {
					return $clean;
				}
				break;

			case 'text':
			default:
				$clean = sanitize_text_field( is_scalar( $value ) ? (string) $value : '' );
				$clean = self::limit_length( $clean, 5000 );
				break;
		}

		if ( $required && ( '' === $clean || ( is_array( $clean ) && ! $clean ) || 0 === $clean ) ) {
			return new WP_Error( 'tusb_required', sprintf(
				/* translators: %s: field label. */
				__( '%s is required.', 'trustusbro-site-manager' ),
				$label
			) );
		}

		return $clean;
	}

	/**
	 * Sanitise a repeater field.
	 *
	 * @param array  $field Field definition.
	 * @param mixed  $value Raw value.
	 * @param string $label Label.
	 * @param array  $errors Error collector.
	 * @param string $doc_key Document key.
	 * @return array
	 */
	private static function repeater( $field, $value, $label, &$errors = array(), $doc_key = '' ) {
		if ( is_string( $value ) ) {
			$decoded = json_decode( $value, true );
			$value   = is_array( $decoded ) ? $decoded : array();
		}
		if ( ! is_array( $value ) ) {
			$value = array();
		}

		$max  = isset( $field['max'] ) ? (int) $field['max'] : 50;
		$sub  = isset( $field['fields'] ) ? $field['fields'] : array();
		$out  = array();
		$seen = array();

		foreach ( $value as $row ) {
			if ( count( $out ) >= $max ) {
				break;
			}
			if ( ! is_array( $row ) ) {
				continue;
			}
			$id = isset( $row['id'] ) ? sanitize_key( $row['id'] ) : '';
			if ( '' === $id || isset( $seen[ $id ] ) ) {
				$id = self::unique_id( 'row', $seen );
			}
			$seen[ $id ] = true;

			$row_errors = array();
			$values     = self::fields( $sub, $row, $label, $row_errors, $doc_key );

			// Drop completely empty rows so blank form rows never create ghosts.
			if ( self::row_is_empty( $values ) ) {
				continue;
			}

			$errors = array_merge( $errors, $row_errors );
			$out[]  = array_merge( array( 'id' => $id ), $values );
		}

		return $out;
	}

	/**
	 * Is a sanitised repeater row empty?
	 *
	 * @param array $values Values.
	 * @return bool
	 */
	private static function row_is_empty( $values ) {
		foreach ( (array) $values as $value ) {
			if ( is_array( $value ) ) {
				if ( $value ) {
					return false;
				}
				continue;
			}
			if ( '' !== $value && 0 !== $value && false !== $value ) {
				return false;
			}
		}
		return true;
	}

	/**
	 * Sanitise a URL, allowing relative links and in-site anchors.
	 *
	 * @param mixed $value Raw value.
	 * @return string
	 */
	public static function url( $value ) {
		$value = is_scalar( $value ) ? trim( (string) $value ) : '';
		if ( '' === $value ) {
			return '';
		}

		// In-page anchors and site-relative paths are always allowed.
		if ( '#' === $value[0] || '/' === $value[0] ) {
			return esc_url_raw( $value );
		}

		// Reject dangerous schemes explicitly, before any escaping happens, so a
		// blocked link is stored as an empty string instead of a broken one.
		$scheme = strtolower( (string) wp_parse_url( $value, PHP_URL_SCHEME ) );
		if ( $scheme && ! in_array( $scheme, array( 'http', 'https', 'mailto', 'tel', 'sms' ), true ) ) {
			return '';
		}
		if ( ! $scheme && preg_match( '/^[a-z][a-z0-9+.\-]*:/i', $value ) ) {
			// Scheme-less dangerous payloads such as `javascript:alert(1)` when
			// wp_parse_url() cannot classify them.
			return '';
		}

		return esc_url_raw( $value, array( 'http', 'https', 'mailto', 'tel', 'sms' ) );
	}

	/**
	 * Sanitise an attachment ID, verifying it is a real image.
	 *
	 * @param mixed $value Raw value (ID, URL or array from a media control).
	 * @return int
	 */
	public static function image_id( $value ) {
		if ( is_array( $value ) ) {
			if ( isset( $value['id'] ) ) {
				$value = $value['id'];
			} elseif ( isset( $value['ID'] ) ) {
				$value = $value['ID'];
			} else {
				return 0;
			}
		}
		if ( is_string( $value ) && ! ctype_digit( $value ) ) {
			// Allow a raw URL: try to resolve it to an attachment.
			$url = esc_url_raw( $value );
			if ( ! $url ) {
				return 0;
			}
			$id = attachment_url_to_postid( $url );
			return $id && wp_attachment_is_image( $id ) ? (int) $id : 0;
		}
		$id = absint( $value );
		if ( ! $id ) {
			return 0;
		}
		if ( 'attachment' !== get_post_type( $id ) || ! wp_attachment_is_image( $id ) ) {
			return 0;
		}
		return $id;
	}

	/**
	 * Robust boolean conversion (handles "false", "0", "off" from JS).
	 *
	 * @param mixed $value Value.
	 * @return bool
	 */
	public static function to_bool( $value ) {
		if ( is_bool( $value ) ) {
			return $value;
		}
		if ( is_numeric( $value ) ) {
			return (int) $value > 0;
		}
		if ( is_string( $value ) ) {
			return in_array( strtolower( trim( $value ) ), array( '1', 'true', 'yes', 'on' ), true );
		}
		return false;
	}

	/**
	 * Trim a string to a maximum length without breaking multibyte characters.
	 *
	 * @param string $value Value.
	 * @param int    $max Maximum length.
	 * @return string
	 */
	private static function limit_length( $value, $max ) {
		if ( function_exists( 'mb_strlen' ) && mb_strlen( $value ) > $max ) {
			return mb_substr( $value, 0, $max );
		}
		if ( ! function_exists( 'mb_strlen' ) && strlen( $value ) > $max ) {
			return substr( $value, 0, $max );
		}
		return $value;
	}

	/**
	 * Generate a unique, readable ID.
	 *
	 * @param string $prefix Prefix.
	 * @param array  $seen Already used IDs.
	 * @return string
	 */
	public static function unique_id( $prefix, $seen = array() ) {
		$prefix = preg_replace( '/[^a-z0-9_]/', '', strtolower( (string) $prefix ) );
		if ( '' === $prefix ) {
			$prefix = 'item';
		}
		do {
			$id = $prefix . '-' . strtolower( wp_generate_password( 6, false, false ) );
		} while ( isset( $seen[ $id ] ) );
		return $id;
	}
}
