<?php
/**
 * Media library manager.
 *
 * Adds alt-text editing, usage lookup and safe replacement for images used
 * across Site Manager content. Replacement copies nothing and deletes nothing:
 * the new attachment is swapped into the stored IDs and the old file stays.
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

/**
 * Media.
 */
class TUSB_Media {

	/**
	 * Register hooks.
	 *
	 * @return void
	 */
	public function hooks() {
		add_filter( 'wp_generate_attachment_metadata', array( $this, 'flag_missing_alt' ), 20, 2 );
		add_filter( 'attachment_fields_to_edit', array( $this, 'noop_fields' ), 10, 2 );
	}

	/**
	 * Placeholder filter to keep the class extensible without altering core UI.
	 *
	 * @param array  $form_fields Fields.
	 * @param object $post Attachment.
	 * @return array
	 */
	public function noop_fields( $form_fields, $post ) {
		return $form_fields;
	}

	/**
	 * Track images that have no alt text (surfaced in the Media Manager).
	 *
	 * @param array $metadata Metadata.
	 * @param int   $attachment_id Attachment ID.
	 * @return array
	 */
	public function flag_missing_alt( $metadata, $attachment_id ) {
		$alt = get_post_meta( $attachment_id, '_wp_attachment_image_alt', true );
		if ( '' === trim( (string) $alt ) ) {
			update_post_meta( $attachment_id, '_tusb_missing_alt', 1 );
		} else {
			delete_post_meta( $attachment_id, '_tusb_missing_alt' );
		}
		return $metadata;
	}

	/**
	 * List image attachments for the dashboard.
	 *
	 * @param array $args Query args: search, page, per_page.
	 * @return array
	 */
	public function list_images( $args = array() ) {
		$per_page = isset( $args['per_page'] ) ? max( 1, min( 100, (int) $args['per_page'] ) ) : 24;
		$page     = isset( $args['page'] ) ? max( 1, (int) $args['page'] ) : 1;

		$query = new WP_Query(
			array(
				'post_type'      => 'attachment',
				'post_mime_type' => 'image',
				'post_status'    => 'inherit',
				'posts_per_page' => $per_page,
				'paged'          => $page,
				's'              => isset( $args['search'] ) ? sanitize_text_field( $args['search'] ) : '',
				'orderby'        => 'date',
				'order'          => 'DESC',
			)
		);

		$items = array();
		foreach ( $query->posts as $post ) {
			$items[] = $this->format( $post->ID );
		}

		return array(
			'items' => $items,
			'total' => (int) $query->found_posts,
			'pages' => (int) $query->max_num_pages,
			'page'  => $page,
		);
	}

	/**
	 * Format one attachment.
	 *
	 * @param int $id Attachment ID.
	 * @return array
	 */
	public function format( $id ) {
		$id   = (int) $id;
		$file = get_attached_file( $id );
		$meta = wp_get_attachment_metadata( $id );

		return array(
			'id'        => $id,
			'title'     => get_the_title( $id ),
			'alt'       => (string) get_post_meta( $id, '_wp_attachment_image_alt', true ),
			'caption'   => wp_get_attachment_caption( $id ),
			'url'       => wp_get_attachment_url( $id ),
			'thumb'     => wp_get_attachment_image_url( $id, 'medium' ) ?: wp_get_attachment_image_url( $id, 'thumbnail' ),
			'mime'      => get_post_mime_type( $id ),
			'width'     => isset( $meta['width'] ) ? (int) $meta['width'] : 0,
			'height'    => isset( $meta['height'] ) ? (int) $meta['height'] : 0,
			'filesize'  => $file && file_exists( $file ) ? size_format( (int) filesize( $file ) ) : '',
			'created'   => get_the_date( 'c', $id ),
			'used_in'   => $this->usage( $id ),
			'missing_alt' => '' === trim( (string) get_post_meta( $id, '_wp_attachment_image_alt', true ) ),
		);
	}

	/**
	 * Find Site Manager documents that reference an attachment.
	 *
	 * @param int $attachment_id Attachment ID.
	 * @return array
	 */
	public function usage( $attachment_id ) {
		$attachment_id = (int) $attachment_id;
		$usage         = array();
		$store         = tusb()->module( 'store' );
		if ( ! $store ) {
			return $usage;
		}

		foreach ( array_keys( tusb_doc_labels() ) as $doc_key ) {
			$published = $store->get( $doc_key, 'published' );
			$draft     = $store->get( $doc_key, 'draft' );
			$search_in = array(
				'published' => $published,
				'draft'     => $draft,
			);
			foreach ( $search_in as $state => $payload ) {
				if ( null === $payload ) {
					continue;
				}
				if ( $this->payload_references( $payload, $attachment_id ) ) {
					$usage[] = array(
						'doc'   => $doc_key,
						'label' => tusb_doc_label( $doc_key ),
						'state' => $state,
					);
					break;
				}
			}
		}

		return $usage;
	}

	/**
	 * Recursively check whether a payload references an attachment ID.
	 *
	 * @param mixed $payload Payload.
	 * @param int   $attachment_id Attachment ID.
	 * @return bool
	 */
	private function payload_references( $payload, $attachment_id ) {
		if ( is_array( $payload ) ) {
			foreach ( $payload as $key => $value ) {
				if ( is_int( $value ) && 'image' === $this->guess_field_kind( $key ) && $value === $attachment_id ) {
					return true;
				}
				if ( is_array( $value ) && $this->payload_references( $value, $attachment_id ) ) {
					return true;
				}
			}
		}
		return false;
	}

	/**
	 * Best-effort field kind from a key name.
	 *
	 * @param string|int $key Key.
	 * @return string
	 */
	private function guess_field_kind( $key ) {
		$image_keys = array( 'image', 'avatar', 'logo', 'og_image', 'cover', 'media', 'photo', 'icon_image' );
		return in_array( (string) $key, $image_keys, true ) ? 'image' : '';
	}

	/**
	 * Update alt text and captions in bulk.
	 *
	 * @param array $updates List of {id, alt, caption}.
	 * @return array|WP_Error
	 */
	public function update_meta( $updates ) {
		if ( ! is_array( $updates ) ) {
			return new WP_Error( 'tusb_invalid', __( 'No changes were received.', 'trustusbro-site-manager' ), array( 'status' => 400 ) );
		}
		$updated = array();
		foreach ( $updates as $update ) {
			$id = isset( $update['id'] ) ? (int) $update['id'] : 0;
			if ( ! $id || 'attachment' !== get_post_type( $id ) ) {
				continue;
			}
			if ( ! current_user_can( 'edit_post', $id ) ) {
				continue;
			}
			if ( array_key_exists( 'alt', $update ) ) {
				update_post_meta( $id, '_wp_attachment_image_alt', sanitize_text_field( (string) $update['alt'] ) );
			}
			if ( array_key_exists( 'title', $update ) ) {
				wp_update_post(
					array(
						'ID'         => $id,
						'post_title' => sanitize_text_field( (string) $update['title'] ),
					)
				);
			}
			if ( array_key_exists( 'caption', $update ) ) {
				wp_update_post(
					array(
						'ID'           => $id,
						'post_excerpt' => sanitize_text_field( (string) $update['caption'] ),
					)
				);
			}
			$alt = get_post_meta( $id, '_wp_attachment_image_alt', true );
			if ( '' === trim( (string) $alt ) ) {
				update_post_meta( $id, '_tusb_missing_alt', 1 );
			} else {
				delete_post_meta( $id, '_tusb_missing_alt' );
			}
			$updated[] = $id;
		}

		return array(
			'updated' => $updated,
			'count'   => count( $updated ),
		);
	}

	/**
	 * Replace an image everywhere it is referenced by Site Manager content.
	 *
	 * The old attachment is left untouched on disk; references are updated to the
	 * new attachment and unpublished drafts are updated as well.
	 *
	 * @param int $old_id Old attachment ID.
	 * @param int $new_id New attachment ID.
	 * @return array|WP_Error
	 */
	public function replace( $old_id, $new_id ) {
		$old_id = TUSB_Sanitizer::image_id( $old_id );
		$new_id = TUSB_Sanitizer::image_id( $new_id );
		if ( ! $old_id || ! $new_id ) {
			return new WP_Error( 'tusb_bad_image', __( 'Both the old and the new image must be valid image attachments.', 'trustusbro-site-manager' ), array( 'status' => 400 ) );
		}

		$store   = tusb()->module( 'store' );
		$changed = array();
		if ( ! $store ) {
			return new WP_Error( 'tusb_no_store', __( 'The content store is unavailable.', 'trustusbro-site-manager' ), array( 'status' => 500 ) );
		}

		foreach ( array_keys( tusb_doc_labels() ) as $doc_key ) {
			$draft = $store->get( $doc_key, 'draft' );
			if ( null === $draft ) {
				continue;
			}
			$replaced = $this->swap( $draft, $old_id, $new_id );
			if ( $replaced !== $draft ) {
				$result = $store->save_draft( $doc_key, $replaced, array( 'label' => __( 'Image replaced', 'trustusbro-site-manager' ) ) );
				if ( ! is_wp_error( $result ) ) {
					$changed[] = $doc_key;
				}
			}
		}

		return array(
			'changed' => $changed,
			'message' => $changed
				? __( 'Image replaced. Publish the affected documents to make it live.', 'trustusbro-site-manager' )
				: __( 'That image is not used in Site Manager content.', 'trustusbro-site-manager' ),
		);
	}

	/**
	 * Recursively swap attachment IDs inside known image fields.
	 *
	 * @param mixed $payload Payload.
	 * @param int   $old_id Old ID.
	 * @param int   $new_id New ID.
	 * @return mixed
	 */
	private function swap( $payload, $old_id, $new_id ) {
		if ( ! is_array( $payload ) ) {
			return $payload;
		}
		foreach ( $payload as $key => $value ) {
			if ( is_int( $value ) || ( is_string( $value ) && ctype_digit( $value ) ) ) {
				if ( 'image' === $this->guess_field_kind( $key ) && (int) $value === $old_id ) {
					$payload[ $key ] = $new_id;
				}
				continue;
			}
			if ( is_array( $value ) ) {
				$payload[ $key ] = $this->swap( $value, $old_id, $new_id );
			}
		}
		return $payload;
	}
}
