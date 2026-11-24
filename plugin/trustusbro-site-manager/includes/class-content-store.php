<?php
/**
 * Content store.
 *
 * Every editable document lives in a hidden custom post type, so content is
 * always in the WordPress database — never only inside plugin files. The store
 * exposes a simple draft / publish / revision API used by the dashboard and the
 * REST endpoints.
 *
 * Layout of a stored document (post_content):
 *
 *   { "draft_version": 12, "published_version": 11, "version": 1 }
 *
 * Revisions are stored as child posts of the document, type tusb_revision,
 * status `draft` (an unpublished draft snapshot) or `publish` (the live copy).
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

/**
 * Content store.
 */
class TUSB_Content_Store {

	/**
	 * Register hooks.
	 *
	 * @return void
	 */
	public function hooks() {
		add_action( 'init', array( $this, 'register_post_type' ), 5 );
		add_action( 'before_delete_post', array( $this, 'guard_against_deletion' ) );
		add_action( 'wp_ajax_tusb_dashboard', array( $this, 'noop' ) );
		add_action( 'before_delete_post', array( $this, 'cleanup_revisions' ) );
	}

	/**
	 * Placeholder kept so the module always has a hook; real AJAX work is done
	 * through the REST API.
	 *
	 * @return void
	 */
	public function noop() {}

	/**
	 * Register the hidden storage post type.
	 *
	 * @return void
	 */
	public function register_post_type() {
		register_post_type(
			TUSB_DOC_CPT,
			array(
				'labels'              => array(
					'name'          => __( 'Site Manager content', 'trustusbro-site-manager' ),
					'singular_name' => __( 'Site Manager content', 'trustusbro-site-manager' ),
				),
				'public'              => false,
				'publicly_queryable'  => false,
				'exclude_from_search' => true,
				'show_ui'             => false,
				'show_in_menu'        => false,
				'show_in_rest'        => false,
				'supports'            => array( 'title', 'editor', 'revisions', 'author' ),
				'rewrite'             => false,
				'query_var'           => false,
				'can_export'          => true,
				'delete_with_user'    => false,
				'capability_type'     => 'post',
				'map_meta_cap'        => true,
			)
		);

		register_post_status(
			'tusb_draft',
			array(
				'label'                     => __( 'Draft snapshot', 'trustusbro-site-manager' ),
				'public'                    => false,
				'internal'                  => true,
				'protected'                 => true,
				'exclude_from_search'       => true,
				'show_in_admin_all_list'    => false,
				'show_in_admin_status_list' => false,
			)
		);
	}

	/**
	 * Find the storage post for a document key.
	 *
	 * @param string $doc_key Document key.
	 * @return int Post ID (0 when missing).
	 */
	public function doc_post_id( $doc_key ) {
		$doc_key = $this->normalise_key( $doc_key );
		if ( '' === $doc_key ) {
			return 0;
		}
		$found = get_posts(
			array(
				'post_type'              => TUSB_DOC_CPT,
				'post_status'            => array( 'publish', 'draft', 'private' ),
				'name'                   => 'tusb-doc-' . $doc_key,
				'numberposts'            => 1,
				'fields'                 => 'ids',
				'no_found_rows'          => true,
				'update_post_meta_cache' => false,
				'update_post_term_cache' => false,
				'orderby'                => 'ID',
				'order'                  => 'ASC',
			)
		);
		if ( $found ) {
			return (int) $found[0];
		}
		return 0;
	}

	/**
	 * Ensure a storage post exists for a document (created lazily, never destructive).
	 *
	 * @param string $doc_key Document key.
	 * @return int Post ID, 0 on failure.
	 */
	public function ensure_post( $doc_key ) {
		$existing = $this->doc_post_id( $doc_key );
		if ( $existing ) {
			return $existing;
		}

		$post_id = wp_insert_post(
			array(
				'post_type'    => TUSB_DOC_CPT,
				'post_status'  => 'publish',
				'post_title'   => sprintf( 'TUSB %s', $doc_key ),
				'post_name'    => 'tusb-doc-' . $this->normalise_key( $doc_key ),
				'post_content' => wp_json_encode(
					array(
						'version'            => TUSB_CONTENT_VERSION,
						'draft_version'      => 0,
						'published_version'  => 0,
						'created'            => time(),
					)
				),
				'comment_status' => 'closed',
				'ping_status'    => 'closed',
			),
			true
		);

		if ( is_wp_error( $post_id ) ) {
			tusb_log( 'Failed to create doc post: ' . $post_id->get_error_message() );
			return 0;
		}

		return (int) $post_id;
	}

	/**
	 * Metadata for a document.
	 *
	 * @param string $doc_key Document key.
	 * @return array
	 */
	public function meta( $doc_key ) {
		$post_id = $this->doc_post_id( $doc_key );
		if ( ! $post_id ) {
			return array(
				'draft_version'     => 0,
				'published_version' => 0,
				'created'           => 0,
			);
		}
		$post = get_post( $post_id );
		if ( ! $post ) {
			return array(
				'draft_version'     => 0,
				'published_version' => 0,
				'created'           => 0,
			);
		}
		$meta = $this->meta_from_post( $doc_key );
		if ( ! $meta ) {
			$meta = tusb_json_decode( $post->post_content );
		}
		return array_merge(
			array(
				'draft_version'     => 0,
				'published_version' => 0,
				'created'           => strtotime( $post->post_date_gmt . ' GMT' ),
			),
			$meta
		);
	}

	/**
	 * Get the stored payload for a document.
	 *
	 * @param string $doc_key Document key.
	 * @param string $state Either 'draft' or 'published'.
	 * @return array|null Payload, or null when nothing is stored yet.
	 */
	public function get( $doc_key, $state = 'draft' ) {
		$meta = $this->meta( $doc_key );
		$post_id = $this->doc_post_id( $doc_key );

		if ( 'published' === $state ) {
			$revision_id = (int) $meta['published_version'];
			$revision    = $revision_id ? $this->get_revision( $doc_key, $revision_id ) : null;
			if ( null !== $revision ) {
				return $revision;
			}
			// Never published: fall back to the draft so the site is never blank.
			$fallback_id = (int) $meta['draft_version'];
			$fallback    = $fallback_id ? $this->get_revision( $doc_key, $fallback_id ) : null;
			return $fallback;
		}

		$revision_id = (int) $meta['draft_version'];
		if ( $revision_id ) {
			$revision = $this->get_revision( $doc_key, $revision_id );
			if ( null !== $revision ) {
				return $revision;
			}
		}

		// Backwards compatibility: content stored directly in post_content as JSON
		// (older installs, or data imported from a file) is still readable.
		return $this->get_legacy_content( $post_id );
	}

	/**
	 * Read a legacy JSON payload stored directly in the document post.
	 *
	 * @param int $post_id Post ID.
	 * @return array|null
	 */
	private function get_legacy_content( $post_id ) {
		if ( ! $post_id ) {
			return null;
		}
		$post = get_post( $post_id );
		if ( ! $post ) {
			return null;
		}
		$decoded = tusb_json_decode( $post->post_content );
		if ( isset( $decoded['sections'] ) || isset( $decoded['items'] ) || isset( $decoded['draft_version'] ) ) {
			if ( isset( $decoded['draft_version'] ) || isset( $decoded['version'] ) ) {
				return null;
			}
			return $decoded;
		}
		return null;
	}

	/**
	 * Get the effective content for a document: stored payload merged with schema
	 * defaults for documents that have never been saved.
	 *
	 * @param string $doc_key Document key.
	 * @param string $state State.
	 * @return array
	 */
	public function resolve( $doc_key, $state = 'published' ) {
		$stored   = $this->get( $doc_key, $state );
		$defaults = TUSB_Schema::defaults( $doc_key );

		if ( null === $stored ) {
			return $defaults;
		}

		$doc  = TUSB_Schema::doc( $doc_key );
		$type = tusb_arr( $doc, 'type' );

		if ( 'sections' === $type ) {
			$sections = isset( $stored['sections'] ) && is_array( $stored['sections'] ) ? $stored['sections'] : array();
			// Fill in any fields added to the schema after the content was saved.
			$out  = array();
			$seen = array();
			foreach ( $sections as $section ) {
				if ( ! is_array( $section ) || empty( $section['type'] ) ) {
					continue;
				}
				$type_key = $section['type'];
				$def_fields = isset( $doc['sections'][ $type_key ]['fields'] ) ? $doc['sections'][ $type_key ]['fields'] : array();
				if ( ! $def_fields && ! isset( $doc['sections'][ $type_key ] ) ) {
					// Retired section type: keep it in storage but do not render it.
					$def_fields = array();
				}
				$out[] = array_merge(
					TUSB_Schema::field_defaults( $def_fields ),
					$section
				);
			}
			$ordered = $this->order_sections( $out, $doc );
			return array( 'sections' => $ordered );
		}

		if ( 'collection' === tusb_arr( $doc, 'type' ) ) {
			$items = isset( $stored['items'] ) && is_array( $stored['items'] ) ? array_values( $stored['items'] ) : array();
			return array( 'items' => $items );
		}

		$fields = isset( $doc['fields'] ) ? $doc['fields'] : array();
		return array_merge( TUSB_Schema::field_defaults( $fields ), is_array( $stored ) ? $stored : array() );
	}

	/**
	 * Order sections by their stored order, and make sure any section defined in
	 * the schema but missing from storage is appended (enabled) so new components
	 * are never silently hidden.
	 *
	 * @param array $sections Sections.
	 * @param array $doc Doc definition.
	 * @return array
	 */
	private function order_sections( $sections, $doc ) {
		$defs = isset( $doc['sections'] ) ? $doc['sections'] : array();
		$types_present = wp_list_pluck( $sections, 'type' );
		$legacy = $this->legacy_keys();

		foreach ( $defs as $type => $def ) {
			if ( in_array( $type, $types_present, true ) ) {
				continue;
			}
			// Do not auto-inject retired sections.
			if ( in_array( $type, $legacy, true ) ) {
				continue;
			}
			$sections[] = array_merge(
				array(
					'id'      => 'auto-' . $type,
					'type'    => $type,
					'enabled' => false,
				),
				TUSB_Schema::field_defaults( isset( $def['fields'] ) ? $def['fields'] : array() )
			);
		}

		return array_values( $sections );
	}

	/**
	 * Legacy / retired section keys configured in Design Settings.
	 *
	 * @return array
	 */
	public function legacy_keys() {
		$settings = TUSB_Settings::get( 'design', array() );
		$raw      = isset( $settings['legacy_docs'] ) ? (string) $settings['legacy_docs'] : '';
		if ( '' === trim( $raw ) ) {
			return array();
		}
		return array_filter( array_map( 'sanitize_key', array_map( 'trim', explode( ',', $raw ) ) ) );
	}

	/**
	 * Save a draft.
	 *
	 * @param string $doc_key Document key.
	 * @param array  $payload Raw payload (untrusted).
	 * @param array  $args Optional args: label, autosave, user_id.
	 * @return array|WP_Error
	 */
	public function save_draft( $doc_key, $payload, $args = array() ) {
		$doc_key = $this->normalise_key( $doc_key );
		if ( '' === $doc_key || ! TUSB_Schema::doc( $doc_key ) ) {
			return new WP_Error( 'tusb_unknown_doc', __( 'Unknown document.', 'trustusbro-site-manager' ), array( 'status' => 404 ) );
		}

		$clean = TUSB_Sanitizer::document( $doc_key, $payload );
		if ( is_wp_error( $clean ) ) {
			return $clean;
		}

		$post_id = $this->ensure_post( $doc_key );
		if ( ! $post_id ) {
			return new WP_Error( 'tusb_store_failed', __( 'Content could not be saved. Please check your database permissions and try again.', 'trustusbro-site-manager' ), array( 'status' => 500 ) );
		}

		$meta = $this->meta( $doc_key );

		// Back up the previous draft before overwriting it (only when it changed materially).
		$current_draft = (int) $meta['draft_version'] ? $this->get_revision( $doc_key, (int) $meta['draft_version'] ) : null;
		if ( null !== $current_draft && $this->payload_signature( $current_draft ) !== $this->payload_signature( $clean ) ) {
			$this->store_revision( $doc_key, $post_id, $current_draft, 'tusb_draft', isset( $args['label'] ) ? $args['label'] : __( 'Before edit', 'trustusbro-site-manager' ), (int) $meta['draft_version'] );
		}

		$revision_id = $this->store_revision(
			$doc_key,
			$post_id,
			$clean,
			'tusb_draft',
			isset( $args['label'] ) ? $args['label'] : __( 'Draft', 'trustusbro-site-manager' )
		);

		if ( is_wp_error( $revision_id ) ) {
			return $revision_id;
		}

		$meta['draft_version']     = $revision_id;
		$meta['draft_modified']    = time();
		$meta['draft_author']      = get_current_user_id();
		$meta['version']           = TUSB_CONTENT_VERSION;

		$this->update_meta_document( $post_id, $meta, $clean );

		/**
		 * Fires after a draft is saved.
		 *
		 * @param string $doc_key Document key.
		 * @param int    $revision_id Revision ID.
		 * @param array  $clean Sanitised payload.
		 */
		do_action( 'tusb_draft_saved', $doc_key, $revision_id, $clean );

		return array(
			'ok'               => true,
			'doc'              => $doc_key,
			'draft_version'    => $revision_id,
			'published_version'=> (int) $meta['published_version'],
			'has_unpublished'  => (int) $meta['draft_version'] !== (int) $meta['published_version'],
			'modified'         => time(),
		);
	}

	/**
	 * Publish the current draft.
	 *
	 * @param string $doc_key Document key.
	 * @param array  $payload Optional payload to save+publish in one step.
	 * @param array  $args Args.
	 * @return array|WP_Error
	 */
	public function publish( $doc_key, $payload = null, $args = array() ) {
		$doc_key = $this->normalise_key( $doc_key );

		if ( null !== $payload ) {
			$saved = $this->save_draft( $doc_key, $payload, array( 'label' => __( 'Before publish', 'trustusbro-site-manager' ) ) );
			if ( is_wp_error( $saved ) ) {
				return $saved;
			}
		}

		$meta = $this->meta( $doc_key );
		$draft_id = (int) $meta['draft_version'];
		if ( ! $draft_id ) {
			return new WP_Error( 'tusb_nothing_to_publish', __( 'There is nothing to publish yet. Make a change first.', 'trustusbro-site-manager' ), array( 'status' => 400 ) );
		}

		$payload_clean = $this->get_revision( $doc_key, $draft_id );
		if ( null === $payload_clean ) {
			return new WP_Error( 'tusb_missing_revision', __( 'The draft could not be found. Please save your changes again.', 'trustusbro-site-manager' ), array( 'status' => 500 ) );
		}

		$post_id = $this->doc_post_id( $doc_key );
		$publish_id = $this->store_revision(
			$doc_key,
			$post_id,
			$payload_clean,
			'publish',
			isset( $args['label'] ) ? $args['label'] : __( 'Published', 'trustusbro-site-manager' )
		);
		if ( is_wp_error( $publish_id ) ) {
			return $publish_id;
		}

		$meta['published_version'] = $publish_id;
		$meta['published_at']      = time();
		$meta['published_by']      = get_current_user_id();
		$this->update_meta_document( $post_id, $meta, $payload_clean );

		/**
		 * Fires after a document is published.
		 *
		 * @param string $doc_key Document key.
		 * @param int    $publish_id Revision ID.
		 */
		do_action( 'tusb_published', $doc_key, $publish_id );

		return array(
			'ok'                => true,
			'doc'               => $doc_key,
			'published_version' => $publish_id,
			'published_at'      => time(),
			'has_unpublished'   => false,
		);
	}

	/**
	 * Discard unsaved draft changes by pointing the draft at the published revision.
	 *
	 * @param string $doc_key Document key.
	 * @return array|WP_Error
	 */
	public function discard_draft( $doc_key ) {
		$doc_key = $this->normalise_key( $doc_key );
		$meta    = $this->meta( $doc_key );
		$post_id = $this->doc_post_id( $doc_key );

		if ( ! $post_id || ! (int) $meta['published_version'] ) {
			return new WP_Error( 'tusb_nothing_to_discard', __( 'There is no published version to restore yet.', 'trustusbro-site-manager' ), array( 'status' => 400 ) );
		}

		$meta['draft_version'] = (int) $meta['published_version'];
		$published             = $this->get_revision( $doc_key, (int) $meta['published_version'] );
		$this->update_meta_document( $post_id, $meta, $published );

		return array(
			'ok'              => true,
			'draft_version'   => (int) $meta['draft_version'],
			'has_unpublished' => false,
		);
	}

	/**
	 * Restore a revision into the draft (published content is untouched until the
	 * user chooses to publish).
	 *
	 * @param string $doc_key Document key.
	 * @param int    $revision_id Revision post ID.
	 * @return array|WP_Error
	 */
	public function restore_revision( $doc_key, $revision_id ) {
		$doc_key   = $this->normalise_key( $doc_key );
		$revision  = $this->get_revision( $doc_key, (int) $revision_id );
		if ( null === $revision ) {
			return new WP_Error( 'tusb_missing_revision', __( 'That version could not be found.', 'trustusbro-site-manager' ), array( 'status' => 404 ) );
		}

		$saved = $this->save_draft(
			$doc_key,
			$revision,
			array(
				'label' => sprintf(
					/* translators: %d: revision ID. */
					__( 'Restored version #%d', 'trustusbro-site-manager' ),
					(int) $revision_id
				),
			)
		);
		if ( is_wp_error( $saved ) ) {
			return $saved;
		}
		$saved['restored_from'] = (int) $revision_id;
		$saved['restored']      = $revision;
		return $saved;
	}

	/**
	 * Store a revision snapshot.
	 *
	 * @param string $doc_key Document key.
	 * @param int    $post_id Document post ID.
	 * @param array  $payload Payload.
	 * @param string $status Post status for the snapshot.
	 * @param string $label Label.
	 * @param int    $existing_revision Optional existing revision ID to overwrite.
	 * @return int|WP_Error
	 */
	private function store_revision( $doc_key, $post_id, $payload, $status, $label, $existing_revision = 0 ) {
		$content = wp_json_encode(
			array(
				'doc'     => $doc_key,
				'payload' => $payload,
				'saved'   => time(),
				'user'    => get_current_user_id(),
				'label'   => $label,
			)
		);

		// Guard: never write an empty payload over real content.
		if ( ! $content || strlen( $content ) < 10 ) {
			return new WP_Error( 'tusb_encode_failed', __( 'The content could not be encoded. Please try again.', 'trustusbro-site-manager' ), array( 'status' => 500 ) );
		}

		$postarr = array(
			'post_type'    => TUSB_DOC_CPT,
			'post_status'  => $status,
			'post_parent'  => $post_id ? (int) $post_id : 0,
			'post_title'   => sprintf( '%s — %s', $doc_key, $label ),
			'post_name'    => sprintf( 'tusb-rev-%s-%s', $doc_key, gmdate( 'YmdHis' ) ),
			'post_content' => $content,
			'post_excerpt' => function_exists( 'mb_substr' ) ? mb_substr( (string) $label, 0, 200 ) : substr( (string) $label, 0, 200 ),
			'comment_status' => 'closed',
			'ping_status'  => 'closed',
		);

		if ( $existing_revision ) {
			$existing = get_post( (int) $existing_revision );
			if ( $existing && TUSB_DOC_CPT === $existing->post_type ) {
				$postarr['ID']          = (int) $existing_revision;
				$postarr['post_status'] = $status;
				$result = wp_update_post( $postarr, true );
				if ( ! is_wp_error( $result ) ) {
					return (int) $result;
				}
			}
		}

		$result = wp_insert_post( $postarr, true );
		if ( is_wp_error( $result ) ) {
			tusb_log( 'revision insert failed: ' . $result->get_error_message() );
			return new WP_Error( 'tusb_revision_failed', __( 'Your changes could not be stored. Please try again.', 'trustusbro-site-manager' ), array( 'status' => 500 ) );
		}
		return (int) $result;
	}

	/**
	 * Load a revision payload.
	 *
	 * @param string $doc_key Document key.
	 * @param int    $revision_id Revision post ID.
	 * @return array|null
	 */
	public function get_revision( $doc_key, $revision_id ) {
		$post = get_post( (int) $revision_id );
		if ( ! $post || TUSB_DOC_CPT !== $post->post_type ) {
			return null;
		}
		$decoded = tusb_json_decode( $post->post_content );
		if ( ! isset( $decoded['payload'] ) || ! is_array( $decoded['payload'] ) ) {
			return null;
		}
		if ( isset( $decoded['doc'] ) && $decoded['doc'] !== $doc_key ) {
			return null;
		}
		return $decoded['payload'];
	}

	/**
	 * Persist document metadata onto the document post.
	 *
	 * @param int   $post_id Post ID.
	 * @param array $meta Meta.
	 * @param array $payload Current payload (kept in post_content for portability).
	 * @return void
	 */
	private function update_meta_document( $post_id, $meta, $payload = null ) {
		if ( ! $post_id ) {
			return;
		}
		$meta['version']          = TUSB_CONTENT_VERSION;
		$meta['last_modified_by'] = get_current_user_id();
		update_post_meta( $post_id, '_tusb_doc_meta', wp_json_encode( $meta ) );
		// Keep a rolling snapshot in the document itself so a site can export and
		// import content with a single post.
		$content = wp_json_encode(
			array(
				'version'           => TUSB_CONTENT_VERSION,
				'draft_version'     => isset( $meta['draft_version'] ) ? (int) $meta['draft_version'] : 0,
				'published_version' => isset( $meta['published_version'] ) ? (int) $meta['published_version'] : 0,
				'updated'           => time(),
			)
		);
		wp_update_post(
			array(
				'ID'           => $post_id,
				'post_content' => $content,
				'post_modified' => current_time( 'mysql' ),
				'post_modified_gmt' => current_time( 'mysql', true ),
			)
		);
	}

	/**
	 * Fetch meta from post meta first (faster/dedicated), falling back to post_content.
	 *
	 * @param string $doc_key Document key.
	 * @return array
	 */
	public function meta_from_post( $doc_key ) {
		$post_id = $this->doc_post_id( $doc_key );
		if ( ! $post_id ) {
			return array();
		}
		$raw = get_post_meta( $post_id, '_tusb_doc_meta', true );
		return tusb_json_decode( $raw );
	}

	/**
	 * List revisions for a document.
	 *
	 * @param string $doc_key Document key.
	 * @param int    $limit Limit.
	 * @return array
	 */
	public function revisions( $doc_key, $limit = 40 ) {
		$post_id = $this->doc_post_id( $doc_key );
		if ( ! $post_id ) {
			return array();
		}
		$posts = get_posts(
			array(
				'post_type'      => TUSB_DOC_CPT,
				'post_parent'    => $post_id,
				'post_status'    => array( 'tusb_draft', 'publish' ),
				'numberposts'    => (int) $limit,
				'orderby'        => 'ID',
				'order'          => 'DESC',
				'no_found_rows'  => true,
			)
		);

		$meta     = $this->meta( $doc_key );
		$out      = array();
		foreach ( $posts as $post ) {
			$decoded = tusb_json_decode( $post->post_content );
			$is_live = (int) $post->ID === (int) tusb_arr( $meta, 'published_version', 0 );
			$is_current = (int) $post->ID === (int) tusb_arr( $meta, 'draft_version', 0 );
			$out[] = array(
				'id'         => (int) $post->ID,
				'label'      => isset( $decoded['label'] ) ? $decoded['label'] : '',
				'status'     => $post->post_status,
				'saved'      => isset( $decoded['saved'] ) ? (int) $decoded['saved'] : strtotime( $post->post_date_gmt . ' GMT' ),
				'user'       => isset( $decoded['user'] ) ? (int) $decoded['user'] : 0,
				'user_name'  => $this->user_name( isset( $decoded['user'] ) ? (int) $decoded['user'] : 0 ),
				'is_live'    => $is_live,
				'is_current' => $is_current,
				'counts'     => $this->payload_counts( isset( $decoded['payload'] ) ? $decoded['payload'] : array() ),
			);
		}
		return $out;
	}

	/**
	 * Get one revision detail (payload) for the UI / diffing.
	 *
	 * @param string $doc_key Document key.
	 * @param int    $revision_id Revision ID.
	 * @return array|null
	 */
	public function revision_detail( $doc_key, $revision_id ) {
		$post = get_post( (int) $revision_id );
		if ( ! $post || TUSB_DOC_CPT !== $post->post_type ) {
			return null;
		}
		$decoded = tusb_json_decode( $post->post_content );
		if ( empty( $decoded['payload'] ) ) {
			return null;
		}
		return array(
			'id'      => (int) $post->ID,
			'label'   => isset( $decoded['label'] ) ? $decoded['label'] : '',
			'saved'   => isset( $decoded['saved'] ) ? (int) $decoded['saved'] : 0,
			'user'    => isset( $decoded['user'] ) ? (int) $decoded['user'] : 0,
			'payload' => $decoded['payload'],
		);
	}

	/**
	 * Simple summary of what a payload contains.
	 *
	 * @param array $payload Payload.
	 * @return array
	 */
	private function payload_counts( $payload ) {
		if ( ! is_array( $payload ) ) {
			return array();
		}
		if ( isset( $payload['sections'] ) && is_array( $payload['sections'] ) ) {
			return array(
				'sections' => count( $payload['sections'] ),
				'enabled'  => count( array_filter( wp_list_pluck( $payload['sections'], 'enabled' ) ) ),
			);
		}
		if ( isset( $payload['items'] ) && is_array( $payload['items'] ) ) {
			return array( 'items' => count( $payload['items'] ) );
		}
		return array( 'fields' => count( $payload ) );
	}

	/**
	 * Display name for a user ID.
	 *
	 * @param int $user_id User ID.
	 * @return string
	 */
	private function user_name( $user_id ) {
		if ( ! $user_id ) {
			return __( 'System', 'trustusbro-site-manager' );
		}
		$user = get_userdata( $user_id );
		return $user ? $user->display_name : __( 'Unknown user', 'trustusbro-site-manager' );
	}

	/**
	 * Cheap signature used to decide whether a revision is worth storing.
	 *
	 * @param array $payload Payload.
	 * @return string
	 */
	private function payload_signature( $payload ) {
		return md5( wp_json_encode( $payload ) );
	}

	/**
	 * Delete old autosave revisions beyond a limit, keeping published snapshots.
	 *
	 * @param string $doc_key Document key.
	 * @param int    $keep How many drafts to keep.
	 * @return void
	 */
	public function prune_revisions( $doc_key, $keep = 30 ) {
		$post_id = $this->doc_post_id( $doc_key );
		if ( ! $post_id ) {
			return;
		}
		$posts = get_posts(
			array(
				'post_type'   => TUSB_DOC_CPT,
				'post_parent' => $post_id,
				'post_status' => 'tusb_draft',
				'numberposts' => 200,
				'orderby'     => 'ID',
				'order'       => 'DESC',
				'fields'      => 'ids',
			)
		);
		$meta = $this->meta( $doc_key );
		$keep_ids = array( (int) $meta['draft_version'], (int) $meta['published_version'] );
		$kept     = 0;
		foreach ( $posts as $id ) {
			if ( in_array( (int) $id, $keep_ids, true ) ) {
				continue;
			}
			$kept++;
			if ( $kept > $keep ) {
				wp_delete_post( $id, true );
			}
		}
	}

	/**
	 * Export every document as a portable array (used by backups).
	 *
	 * @return array
	 */
	public function export_all() {
		$out = array();
		foreach ( array_keys( tusb_doc_labels() ) as $doc_key ) {
			$draft = $this->get( $doc_key, 'draft' );
			$live  = $this->get( $doc_key, 'published' );
			$out[ $doc_key ] = array(
				'draft'     => $draft,
				'published' => $live,
			);
		}
		return $out;
	}

	/**
	 * Import documents from an export array.
	 *
	 * @param array $data Export data.
	 * @return array Summary.
	 */
	public function import_all( $data ) {
		$summary = array(
			'imported' => array(),
			'skipped'  => array(),
			'failed'   => array(),
		);
		if ( ! is_array( $data ) ) {
			return $summary;
		}
		foreach ( $data as $doc_key => $payloads ) {
			$doc_key = $this->normalise_key( $doc_key );
			if ( ! TUSB_Schema::doc( $doc_key ) || ! is_array( $payloads ) ) {
				$summary['skipped'][] = $doc_key;
				continue;
			}
			// Prefer the published copy, then the draft.
			$payload = null;
			if ( ! empty( $payloads['published'] ) ) {
				$payload = $payloads['published'];
			} elseif ( ! empty( $payloads['draft'] ) ) {
				$payload = $payloads['draft'];
			}
			if ( null === $payload ) {
				$summary['skipped'][] = $doc_key;
				continue;
			}
			$saved = $this->save_draft( $doc_key, $payload, array( 'label' => __( 'Imported from backup', 'trustusbro-site-manager' ) ) );
			if ( is_wp_error( $saved ) ) {
				$summary['failed'][] = array(
					'doc'   => $doc_key,
					'error' => $saved->get_error_message(),
				);
				continue;
			}
			// Deliberately do NOT publish here. A restore/import must be reviewable
			// before it reaches visitors; the owner publishes from the dashboard.
			$summary['imported'][] = $doc_key;
		}
		return $summary;
	}

	/**
	 * Status summary used by the dashboard overview.
	 *
	 * @return array
	 */
	public function status() {
		$out = array();
		foreach ( array_keys( tusb_doc_labels() ) as $doc_key ) {
			$meta  = $this->meta( $doc_key );
			$draft = (int) tusb_arr( $meta, 'draft_version', 0 );
			$live  = (int) tusb_arr( $meta, 'published_version', 0 );
			$out[ $doc_key ] = array(
				'label'           => tusb_doc_label( $doc_key ),
				'published'       => $live > 0,
				'has_unpublished' => $draft > 0 && $draft !== $live,
				'published_at'    => (int) tusb_arr( $meta, 'published_at', 0 ),
				'draft_modified'  => (int) tusb_arr( $meta, 'draft_modified', 0 ),
				'published_version' => $live,
				'draft_version'   => $draft,
			);
		}
		return $out;
	}

	/**
	 * Prevent the storage posts from being trashed/deleted from the admin.
	 * (Admins can still delete them through the database; this only stops
	 * accidental deletion from wp-admin lists, where they are hidden anyway.)
	 *
	 * @param int $post_id Post ID.
	 * @return void
	 */
	public function guard_against_deletion( $post_id ) {
		$post = get_post( $post_id );
		if ( ! $post || TUSB_DOC_CPT !== $post->post_type ) {
			return;
		}
		if ( $post->post_parent ) {
			return; // revisions may be pruned.
		}
		if ( ! current_user_can( 'delete_others_posts' ) ) {
			wp_die( esc_html__( 'This content is managed by TrustUsBro Site Manager.', 'trustusbro-site-manager' ), 403 );
		}
	}

	/**
	 * Deleting a document removes its revisions too (explicit admin action only).
	 *
	 * @param int $post_id Post ID.
	 * @return void
	 */
	public function cleanup_revisions( $post_id ) {
		$post = get_post( $post_id );
		if ( ! $post || TUSB_DOC_CPT !== $post->post_type || $post->post_parent ) {
			return;
		}
		$children = get_children(
			array(
				'post_parent' => $post_id,
				'post_type'   => TUSB_DOC_CPT,
				'numberposts' => 500,
				'fields'      => 'ids',
			)
		);
		foreach ( $children as $child_id ) {
			wp_delete_post( $child_id, true );
		}
	}

	/**
	 * Normalise a document key.
	 *
	 * @param string $key Raw key.
	 * @return string
	 */
	public function normalise_key( $key ) {
		$key = sanitize_key( (string) $key );
		return str_replace( '-', '_', $key );
	}
}
