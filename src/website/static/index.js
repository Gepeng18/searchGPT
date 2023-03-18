$(document).ready(function () {
    $('form').submit(function (event) {
        event.preventDefault();

        let socket = io.connect();
        socket.on('search-step', function (message) {
            if (message) {
                console.log("search-step: " + message.msg);
                $('#search-result-step').html(message.html);
            } else {
            }
        });

        socket.on('openai-stream', function (message) {
            console.log(message.msg);
            $('#result-text')[0].append(message.msg);
        });

        let search_text = $('#form1').val();

        $('#result-text')[0].innerHTML = '';
        $('#ref-links')[0].innerHTML = '';
        $('#search-query')[0].innerHTML = search_text;

        $('#search-btn')[0].disabled = true;
        $('#search-result-spinner').addClass('d-flex');
        // $('#search-results').hide();
        $('#explain_results').hide();
        $.ajax({
            url: '/search',
            type: 'POST',
            data: {
                q: search_text,
                bing_search_subscription_key: $('#bing_search_subscription_key').val(),
                openai_api_key: $('#openai_api_key').val(),
                is_use_source: $('input[name="is_use_source"]')[0].checked,
                llm_service_provider: $('#llm_service_provider').val(),
                llm_model: $('#llm_model').val()
            },
            success: function (response) {
                $('#' + response.id).html(response.html)
                $('#explain_results').html(response.explain_html)
                $('#search-btn')[0].disabled = false;
                $('#search-result-spinner').removeClass('d-flex');
                // $('#search-results').show();
                $('#explain_results').show();

                socket.disconnect();
            },
            error: function (error) {
                console.log(error)
                $('#explain_results').html(response.explain_html)
                $('#search-btn')[0].disabled = false;
                $('#search-result-spinner').removeClass('d-flex');
                // $('#search-results').show();
                $('#explain_results').show();

                socket.disconnect();
            }
        })
    })
})