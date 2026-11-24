<?php
/**
 * REST API.
 *
 * All dashboard operations go through signed REST routes with capability checks
 * and nonces. Nothing here bypasses the sanitizer.
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

/**
 * REST controller.
 */
class TUSB_REST {

	/**
	 * Namespace.
	 */
	const NS = 'tusb/v1';

	/**
	 * Register hooks.
	 *
	 * @return void
	 */
	public function hooks() {
		add_action( 'rest_api_init', array( $this, 'register_routes' ) );
	}

	/**
	 * Register routes.
	 *
	 * @return void
	 */
	public function register_routes() {
		$manage  = array( $this, 'can_manage' );
		$restore = array( $this, 'can_restore' );

		register_rest_route(
			self::NS,
			'/bootstrap',
			array(
				'methods'             => WP_REST_Server::READABLE,
				'callback'            => array( $this, 'bootstrap' ),
				'permission_callback' => $manage,
			)
		);

		register_rest_route(
			self::NS,
			'/health',
			array(
				'methods'             => WP_REST_Server::READABLE,
				'callback'            => array( $this, 'health' ),
				'permission_callback' => $manage,
			)
		);

		register_rest_route(
			self::NS,
			'/docs/(?P<doc>[a-z0-9_]+)',
			array(
				array(
					'methods'             => WP_REST_Server::READABLE,
					'callback'            => array( $this, 'get_doc' ),
					'permission_callback' => $manage,
					'args'                => array(
						'doc' => array(
							'required'          => true,
							'sanitize_callback' => 'sanitize_key',
						),
					),
				),
			)
		);

		register_rest_route(
			self::NS,
			'/docs/(?P<doc>[a-z0-9_]+)/draft',
			array(
				'methods'             => WP_REST_Server::CREATABLE,
				'callback'            => array( $this, 'save_draft' ),
				'permission_callback' => $manage,
			)
		);

		register_rest_route(
			self::NS,
			'/docs/(?P<doc>[a-z0-9_]+)/publish',
			array(
				'methods'             => WP_REST_Server::CREATABLE,
				'callback'            => array( $this, 'publish' ),
				'permission_callback' => $manage,
			)
		);

		register_rest_route(
			self::NS,
			'/docs/(?P<doc>[a-z0-9_]+)/discard',
			array(
				'methods'             => WP_REST_Server::CREATABLE,
				'callback'            => array( $this, 'discard' ),
				'permission_callback' => $manage,
			)
		);

		register_rest_route(
			self::NS,
			'/docs/(?P<doc>[a-z0-9_]+)/revisions',
			array(
				'methods'             => WP_REST_Server::READABLE,
				'callback'            => array( $this, 'revisions' ),
				'permission_callback' => $manage,
			)
		);

		register_rest_route(
			self::NS,
			'/docs/(?P<doc>[a-z0-9_]+)/restore',
			array(
				'methods'             => WP_REST_Server::CREATABLE,
				'callback'            => array( $this, 'restore_revision' ),
				'permission_callback' => $manage,
			)
		);

		register_rest_route(
			self::NS,
			'/revisions/(?P<doc>[a-z0-9_]+)/(?P<id>\d+)',
			array(
				'methods'             => WP_REST_Server::READABLE,
				'callback'            => array( $this, 'revision_detail' ),
				'permission_callback' => $manage,
			)
		);

		register_rest_route(
			self::NS,
			'/media',
			array(
				'methods'             => WP_REST_Server::READABLE,
				'callback'            => array( $this, 'media_index' ),
				'permission_callback' => $manage,
			)
		);

		register_rest_route(
			self::NS,
			'/media/update',
			array(
				'methods'             => WP_REST_Server::CREATABLE,
				'callback'            => array( $this, 'media_update' ),
				'permission_callback' => $manage,
			)
		);

		register_rest_route(
			self::NS,
			'/media/replace',
			array(
				'methods'             => WP_REST_Server::CREATABLE,
				'callback'            => array( $this, 'media_replace' ),
				'permission_callback' => $manage,
			)
		);

		register_rest_route(
			self::NS,
			'/backups',
			array(
				array(
					'methods'             => WP_REST_Server::READABLE,
					'callback'            => array( $this, 'backups_index' ),
					'permission_callback' => $manage,
				),
				array(
					'methods'             => WP_REST_Server::CREATABLE,
					'callback'            => array( $this, 'backups_create' ),
					'permission_callback' => $restore,
				),
			)
		);

		register_rest_route(
			self::NS,
			'/backups/(?P<id>[a-zA-Z0-9\-]+)/restore',
			array(
				'methods'             => WP_REST_Server::CREATABLE,
				'callback'            => array( $this, 'backups_restore' ),
				'permission_callback' => $restore,
			)
		);

		register_rest_route(
			self::NS,
			'/backups/(?P<id>[a-zA-Z0-9\-]+)/download',
			array(
				'methods'             => WP_REST_Server::READABLE,
				'callback'            => array( $this, 'backups_download' ),
				'permission_callback' => $restore,
			)
		);

		register_rest_route(
			self::NS,
			'/backups/download-current',
			array(
				'methods'             => WP_REST_Server::READABLE,
				'callback'            => array( $this, 'backups_download_current' ),
				'permission_callback' => $restore,
			)
		);

		// NOTE: the wildcard routes below must stay last. WordPress matches routes in
		// registration order, so registering `/backups/(?P<id>...)` before the literal
		// `/backups/download-current` would make the literal one unreachable.
		register_rest_route(
			self::NS,
			'/backups/upload',
			array(
				'methods'             => WP_REST_Server::CREATABLE,
				'callback'            => array( $this, 'backups_upload' ),
				'permission_callback' => $restore,
			)
		);

		register_rest_route(
			self::NS,
			'/backups/(?P<id>[a-zA-Z0-9\-]+)',
			array(
				array(
					'methods'             => WP_REST_Server::DELETABLE,
					'callback'            => array( $this, 'backups_delete' ),
					'permission_callback' => $restore,
				),
				array(
					'methods'             => WP_REST_Server::READABLE,
					'callback'            => array( $this, 'backups_read' ),
					'permission_callback' => $manage,
				),
			)
		);


		register_rest_route(
			self::NS,
			'/blog',
			array(
				'methods'             => WP_REST_Server::READABLE,
				'callback'            => array( $this, 'blog_index' ),
				'permission_callback' => $manage,
			)
		);

		register_rest_route(
			self::NS,
			'/blog/post',
			array(
				'methods'             => WP_REST_Server::CREATABLE,
				'callback'            => array( $this, 'blog_save_post' ),
				'permission_callback' => $manage,
			)
		);

		register_rest_route(
			self::NS,
			'/blog/category',
			array(
				array(
					'methods'             => WP_REST_Server::CREATABLE,
					'callback'            => array( $this, 'blog_save_category' ),
					'permission_callback' => $manage,
				),
				array(
					'methods'             => WP_REST_Server::DELETABLE,
					'callback'            => array( $this, 'blog_delete_category' ),
					'permission_callback' => $manage,
				),
			)
		);

		register_rest_route(
			self::NS,
			'/seo',
			array(
				'methods'             => WP_REST_Server::READABLE,
				'callback'            => array( $this, 'seo_report' ),
				'permission_callback' => $manage,
			)
		);

		register_rest_route(
			self::NS,
			'/demo',
			array(
				'methods'             => WP_REST_Server::CREATABLE,
				'callback'            => array( $this, 'load_demo' ),
				'permission_callback' => $restore,
			)
		);

		register_rest_route(
			self::NS,
			'/nav-menus',
			array(
				'methods'             => WP_REST_Server::READABLE,
				'callback'            => array( $this, 'nav_menus' ),
				'permission_callback' => $manage,
			)
		);
	}

	/*
	 * ---------------------------------------------------------------------
	 * Permissions
	 * ---------------------------------------------------------------------
	 */

	/**
	 * Capability check for content management.
	 *
	 * @return bool
	 */
	public function can_manage() {
		return TUSB_Capabilities::can_manage();
	}

	/**
	 * Capability check for restore operations.
	 *
	 * @return bool
	 */
	public function can_restore() {
		return TUSB_Capabilities::can_restore();
	}

	/*
	 * ---------------------------------------------------------------------
	 * Handlers
	 * ---------------------------------------------------------------------
	 */

	/**
	 * Bootstrap payload for the dashboard app.
	 *
	 * @return WP_REST_Response
	 */
	public function bootstrap() {
		$store = tusb()->module( 'store' );

		$schema = TUSB_Schema::all();
		// Attach field counts so the UI can summarise sections cheaply.
		foreach ( $schema as $key => $doc ) {
			$schema[ $key ]['key'] = $key;
			$schema[ $key ]['label'] = tusb_doc_label( $key );
		}

		return new WP_REST_Response(
			array(
				'schema'      => $schema,
				'status'      => $store ? $store->status() : array(),
				'settings'    => TUSB_Settings::all(),
				'design'      => TUSB_Design::tokens(),
				'health'      => TUSB_Compat::report(),
				'seo'         => array(
					'prints_meta'   => TUSB_SEO::prints_meta(),
					'other_plugins' => TUSB_Compat::seo_plugins(),
				),
				'backups'     => array(),
				'user'        => array(
					'id'        => get_current_user_id(),
					'name'      => wp_get_current_user()->display_name,
					'can_manage'=> $this->can_manage(),
					'can_restore'=> $this->can_restore(),
				),
				'links'       => array(
					'admin'    => admin_url(),
					'site'     => home_url( '/' ),
					'media'    => admin_url( 'upload.php' ),
					'new_post' => admin_url( 'post-new.php' ),
					'menus'    => admin_url( 'nav-menus.php' ),
					'permalinks' => admin_url( 'options-permalink.php' ),
				),
				'media'       => array(
					// Mirrors the localised strings in class-admin.php so any client of
					// this API (including the standalone demo) can label media controls.
					'libraryTitle'  => __( 'Choose an image', 'trustusbro-site-manager' ),
					'libraryButton' => __( 'Use this image', 'trustusbro-site-manager' ),
					'removeTitle'   => __( 'Remove image', 'trustusbro-site-manager' ),
				),
				'defaults'    => array(
					'page_docs'       => tusb_page_docs(),
					'collection_docs' => tusb_collection_docs(),
					'doc_labels'      => tusb_doc_labels(),
				),
				'rest_url'    => rest_url( self::NS ),
				'version'     => TUSB_VERSION,
				'install'     => array(
					'activated' => get_option( 'tusb_installed_at' ),
					'seeded'    => get_option( 'tusb_seeded' ),
					'last_backup' => get_option( 'tusb_last_backup' ),
				),
			),
			200
		);
	}

	/**
	 * Compatibility/health report.
	 *
	 * @return WP_REST_Response
	 */
	public function health() {
		return new WP_REST_Response( TUSB_Compat::report(), 200 );
	}

	/**
	 * Read one document (draft + published + meta + revisions).
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response|WP_Error
	 */
	public function get_doc( $request ) {
		$store   = tusb()->module( 'store' );
		$doc_key = $store->normalise_key( $request['doc'] );
		$doc     = TUSB_Schema::doc( $doc_key );
		if ( ! $doc ) {
			return new WP_Error( 'tusb_unknown_doc', __( 'Unknown document.', 'trustusbro-site-manager' ), array( 'status' => 404 ) );
		}

		$meta     = $store->meta( $doc_key );
		$draft    = $store->resolve( $doc_key, 'draft' );
		$published= $store->resolve( $doc_key, 'published' );

		return new WP_REST_Response(
			array(
				'doc'       => $doc_key,
				'schema'    => $doc,
				'draft'     => $draft,
				'published' => $published,
				'meta'      => $meta,
				'has_unpublished' => (int) $meta['draft_version'] !== (int) $meta['published_version'],
				'revisions' => $store->revisions( $doc_key, 20 ),
				'preview'   => tusb_preview_url( $doc_key ),
			),
			200
		);
	}

	/**
	 * Save a draft.
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response|WP_Error
	 */
	public function save_draft( $request ) {
		$store   = tusb()->module( 'store' );
		$doc_key = $store->normalise_key( $request['doc'] );
		$payload = $request->get_param( 'payload' );
		$label   = $request->get_param( 'label' );

		$result = $store->save_draft(
			$doc_key,
			$payload,
			array( 'label' => $label ? sanitize_text_field( $label ) : __( 'Editing in dashboard', 'trustusbro-site-manager' ) )
		);

		if ( is_wp_error( $result ) ) {
			return $result;
		}

		$store->prune_revisions( $doc_key );

		return new WP_REST_Response( $result, 200 );
	}

	/**
	 * Publish a draft (optionally saving a payload first).
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response|WP_Error
	 */
	public function publish( $request ) {
		$store   = tusb()->module( 'store' );
		$doc_key = $store->normalise_key( $request['doc'] );
		$payload = $request->get_param( 'payload' );

		// Always snapshot before publishing.
		$backup = tusb()->module( 'backup' );
		if ( $backup instanceof TUSB_Backup ) {
			$backup->create( 'before-publish-' . $doc_key );
		}

		$result = $store->publish( $doc_key, null === $payload ? null : $payload );
		if ( is_wp_error( $result ) ) {
			return $result;
		}

		$result['published'] = $store->resolve( $doc_key, 'published' );
		return new WP_REST_Response( $result, 200 );
	}

	/**
	 * Discard draft changes.
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response|WP_Error
	 */
	public function discard( $request ) {
		$store   = tusb()->module( 'store' );
		$doc_key = $store->normalise_key( $request['doc'] );
		$result  = $store->discard_draft( $doc_key );
		if ( is_wp_error( $result ) ) {
			return $result;
		}
		$result['draft'] = $store->resolve( $doc_key, 'draft' );
		return new WP_REST_Response( $result, 200 );
	}

	/**
	 * List revisions.
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response
	 */
	public function revisions( $request ) {
		$store   = tusb()->module( 'store' );
		$doc_key = $store->normalise_key( $request['doc'] );
		return new WP_REST_Response(
			array(
				'doc'       => $doc_key,
				'revisions' => $store->revisions( $doc_key, 50 ),
			),
			200
		);
	}

	/**
	 * Revision detail.
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response|WP_Error
	 */
	public function revision_detail( $request ) {
		$store   = tusb()->module( 'store' );
		$doc_key = $store->normalise_key( $request['doc'] );
		$detail  = $store->revision_detail( $doc_key, (int) $request['id'] );
		if ( ! $detail ) {
			return new WP_Error( 'tusb_missing_revision', __( 'That version could not be found.', 'trustusbro-site-manager' ), array( 'status' => 404 ) );
		}
		return new WP_REST_Response( $detail, 200 );
	}

	/**
	 * Restore a revision into the draft.
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response|WP_Error
	 */
	public function restore_revision( $request ) {
		$store   = tusb()->module( 'store' );
		$doc_key = $store->normalise_key( $request['doc'] );
		$result  = $store->restore_revision( $doc_key, (int) $request->get_param( 'revision_id' ) );
		if ( is_wp_error( $result ) ) {
			return $result;
		}
		$result['draft'] = $store->resolve( $doc_key, 'draft' );
		return new WP_REST_Response( $result, 200 );
	}

	/**
	 * Media index.
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response
	 */
	public function media_index( $request ) {
		$media = tusb()->module( 'media' );
		return new WP_REST_Response(
			$media->list_images(
				array(
					'search'   => (string) $request->get_param( 'search' ),
					'page'     => (int) $request->get_param( 'page' ) ?: 1,
					'per_page' => (int) $request->get_param( 'per_page' ) ?: 24,
				)
			),
			200
		);
	}

	/**
	 * Update media metadata.
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response|WP_Error
	 */
	public function media_update( $request ) {
		$media  = tusb()->module( 'media' );
		$result = $media->update_meta( $request->get_param( 'updates' ) );
		if ( is_wp_error( $result ) ) {
			return $result;
		}
		return new WP_REST_Response( $result, 200 );
	}

	/**
	 * Replace an image across content.
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response|WP_Error
	 */
	public function media_replace( $request ) {
		$media  = tusb()->module( 'media' );
		$result = $media->replace( (int) $request->get_param( 'old_id' ), (int) $request->get_param( 'new_id' ) );
		if ( is_wp_error( $result ) ) {
			return $result;
		}
		return new WP_REST_Response( $result, 200 );
	}

	/**
	 * Backups index.
	 *
	 * @return WP_REST_Response
	 */
	public function backups_index() {
		$backup = tusb()->module( 'backup' );
		$index  = $backup->index();
		foreach ( $index as &$entry ) {
			$entry['created_label'] = wp_date( get_option( 'date_format' ) . ' ' . get_option( 'time_format' ), $entry['created'] );
			$entry['size_label']    = size_format( $entry['size'] );
			$entry['user_name']     = ( $user = get_userdata( (int) $entry['user'] ) ) ? $user->display_name : __( 'System', 'trustusbro-site-manager' );
		}
		unset( $entry );

		return new WP_REST_Response(
			array(
				'backups'  => $index,
				'location' => 'wp-content/uploads/trustusbro-backups/',
				'max'      => TUSB_Backup::MAX_BACKUPS,
				'next'     => wp_next_scheduled( 'tusb_daily_backup' ),
				'last'     => get_option( 'tusb_last_backup' ),
			),
			200
		);
	}

	/**
	 * Create a backup.
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response|WP_Error
	 */
	public function backups_create( $request ) {
		$backup = tusb()->module( 'backup' );
		$result = $backup->create( $request->get_param( 'reason' ) ? sanitize_key( $request->get_param( 'reason' ) ) : 'manual' );
		if ( is_wp_error( $result ) ) {
			return $result;
		}
		$backup->prune();
		return new WP_REST_Response( $result, 201 );
	}

	/**
	 * Delete a backup.
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response|WP_Error
	 */
	public function backups_delete( $request ) {
		$backup = tusb()->module( 'backup' );
		$result = $backup->delete( $request['id'] );
		if ( is_wp_error( $result ) ) {
			return $result;
		}
		return new WP_REST_Response( $result, 200 );
	}

	/**
	 * Read backup metadata + document keys (not the whole payload).
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response|WP_Error
	 */
	public function backups_read( $request ) {
		$backup = tusb()->module( 'backup' );
		$data   = $backup->read( $request['id'] );
		if ( is_wp_error( $data ) ) {
			return $data;
		}
		return new WP_REST_Response(
			array(
				'created'   => isset( $data['created'] ) ? $data['created'] : 0,
				'reason'    => isset( $data['reason'] ) ? $data['reason'] : '',
				'site'      => isset( $data['site'] ) ? $data['site'] : array(),
				'documents' => array_keys( isset( $data['documents'] ) ? $data['documents'] : array() ),
			),
			200
		);
	}

	/**
	 * Restore a backup.
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response|WP_Error
	 */
	public function backups_restore( $request ) {
		$backup = tusb()->module( 'backup' );
		$result = $backup->restore( $request['id'] );
		if ( is_wp_error( $result ) ) {
			return $result;
		}
		return new WP_REST_Response( $result, 200 );
	}

	/**
	 * Download a backup as JSON.
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response|WP_Error
	 */
	public function backups_download( $request ) {
		$backup = tusb()->module( 'backup' );
		$path   = $backup->path_for( $request['id'] );
		if ( is_wp_error( $path ) ) {
			return $path;
		}
		$raw = file_get_contents( $path ); // phpcs:ignore WordPress.WP.AlternativeFunctions
		if ( false === $raw ) {
			return new WP_Error( 'tusb_backup_read', __( 'The backup file could not be read.', 'trustusbro-site-manager' ), array( 'status' => 500 ) );
		}
		$response = new WP_REST_Response( json_decode( $raw, true ), 200 );
		$response->header( 'Content-Disposition', 'attachment; filename="' . basename( $path ) . '"' );
		return $response;
	}

	/**
	 * Download the current content as a backup JSON file.
	 *
	 * @return WP_REST_Response|WP_Error
	 */
	public function backups_download_current() {
		$backup = tusb()->module( 'backup' );
		$raw    = $backup->export_string();
		$data   = json_decode( $raw, true );
		if ( ! is_array( $data ) ) {
			return new WP_Error( 'tusb_export_failed', __( 'The export could not be generated.', 'trustusbro-site-manager' ), array( 'status' => 500 ) );
		}
		$response = new WP_REST_Response( $data, 200 );
		$response->header( 'Content-Disposition', 'attachment; filename="tusb-content-' . gmdate( 'Ymd-His' ) . '.json"' );
		return $response;
	}

	/**
	 * Upload a backup file (multipart).
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response|WP_Error
	 */
	public function backups_upload( $request ) {
		$files = $request->get_file_params();
		if ( empty( $files['backup'] ) ) {
			return new WP_Error( 'tusb_upload', __( 'Please choose a backup file.', 'trustusbro-site-manager' ), array( 'status' => 400 ) );
		}
		$backup = tusb()->module( 'backup' );
		$result = $backup->import_file( $files['backup'] );
		if ( is_wp_error( $result ) ) {
			return $result;
		}
		return new WP_REST_Response( $result, 200 );
	}

	/**
	 * Blog index.
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response
	 */
	public function blog_index( $request ) {
		$blog = tusb()->module( 'blog' );
		return new WP_REST_Response(
			$blog->listing(
				array(
					'status'   => (string) $request->get_param( 'status' ),
					'category' => (string) $request->get_param( 'category' ),
					'page'     => (int) $request->get_param( 'page' ) ?: 1,
				)
			),
			200
		);
	}

	/**
	 * Save a blog post.
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response|WP_Error
	 */
	public function blog_save_post( $request ) {
		$blog   = tusb()->module( 'blog' );
		$result = $blog->save_post( (array) $request->get_param( 'post' ) );
		if ( is_wp_error( $result ) ) {
			return $result;
		}
		return new WP_REST_Response( $result, 200 );
	}

	/**
	 * Save a category.
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response|WP_Error
	 */
	public function blog_save_category( $request ) {
		$blog   = tusb()->module( 'blog' );
		$result = $blog->save_category( (array) $request->get_param( 'category' ) );
		if ( is_wp_error( $result ) ) {
			return $result;
		}
		return new WP_REST_Response( $result, 200 );
	}

	/**
	 * Delete a category.
	 *
	 * @param WP_REST_Request $request Request.
	 * @return WP_REST_Response|WP_Error
	 */
	public function blog_delete_category( $request ) {
		$blog   = tusb()->module( 'blog' );
		$result = $blog->delete_category( (int) $request->get_param( 'id' ) );
		if ( is_wp_error( $result ) ) {
			return $result;
		}
		return new WP_REST_Response( $result, 200 );
	}

	/**
	 * SEO report.
	 *
	 * @return WP_REST_Response
	 */
	public function seo_report() {
		$seo = tusb()->module( 'seo' );
		return new WP_REST_Response( $seo->report(), 200 );
	}

	/**
	 * Load demo content into the collections.
	 *
	 * @return WP_REST_Response|WP_Error
	 */
	public function load_demo() {
		require_once TUSB_DIR . 'includes/defaults.php';
		$store = tusb()->module( 'store' );
		$demo  = tusb_demo_content();
		$done  = array();

		foreach ( $demo as $doc_key => $payload ) {
			$existing = $store->get( $doc_key, 'draft' );
			$items    = null !== $existing && isset( $existing['items'] ) ? $existing['items'] : array();
			if ( $items ) {
				// Never overwrite real content with demo content.
				continue;
			}
			$saved = $store->save_draft( $doc_key, $payload, array( 'label' => __( 'Demo content', 'trustusbro-site-manager' ) ) );
			if ( ! is_wp_error( $saved ) ) {
				$store->publish( $doc_key, null, array( 'label' => __( 'Demo content', 'trustusbro-site-manager' ) ) );
				$done[] = $doc_key;
			}
		}

		return new WP_REST_Response(
			array(
				'ok'      => true,
				'loaded'  => $done,
				'message' => $done
					? __( 'Demo content loaded. Replace the placeholders with your real content before publishing.', 'trustusbro-site-manager' )
					: __( 'Nothing was loaded: these collections already contain your content, which was not touched.', 'trustusbro-site-manager' ),
			),
			200
		);
	}

	/**
	 * WordPress nav menus for the header selector.
	 *
	 * @return WP_REST_Response
	 */
	public function nav_menus() {
		$menus = wp_get_nav_menus();
		$out   = array();
		foreach ( $menus as $menu ) {
			$out[] = array(
				'id'   => $menu->term_id,
				'name' => $menu->name,
				'slug' => $menu->slug,
			);
		}
		return new WP_REST_Response( array( 'menus' => $out ), 200 );
	}
}
